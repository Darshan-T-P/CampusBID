"""Campus-only trust: who may register, and proving they own the email they gave."""

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.config import settings
from app.core.security import hash_password
from app.models import EmailVerification, PasswordReset, User
from app.services import mailer
from app.services.errors import AccountError

logger = logging.getLogger("campusbid.accounts")


def normalize_email(email: str) -> str:
    """One canonical form per mailbox: trimmed, lowercase, and without any "+tag".

    So "Asha+shop@College.edu" and "asha@college.edu" are the same account.
    """
    local, _, domain = email.strip().lower().rpartition("@")
    local = local.split("+", 1)[0]
    if not local or not domain:
        raise AccountError("Enter a valid email address")
    return f"{local}@{domain}"


def domain_allowed(email: str) -> bool:
    """Exact domain match (or a real subdomain), never a suffix match on the raw string.

    "college.edu" accepts a@college.edu and a@cs.college.edu, but not a@evilcollege.edu
    or a@college.edu.evil.com.
    """
    domains = settings.email_domains
    if not domains:
        return True  # only possible in dev mode: startup refuses to run otherwise
    domain = email.rpartition("@")[2]
    return any(domain == d or domain.endswith("." + d) for d in domains)


def check_registration_email(email: str) -> str:
    """Normalize and enforce the campus-domain rule. Returns the canonical email."""
    email = normalize_email(email)
    suffix = settings.required_email_suffix.strip().lower()
    if suffix and not email.endswith(suffix):
        raise AccountError(f"Please use your campus email address (it ends in {suffix})")
    if not domain_allowed(email):
        raise AccountError("Please use your campus email address")
    return email


# --- verification codes -----------------------------------------------------


def _hash_code(user_id: int, code: str, purpose: str = "verify") -> str:
    # Keyed hash: a leaked database row can't be reversed into a code without the secret. The purpose is part of
    # the input, so a code emailed for verifying an address can never be replayed to reset a password.
    return hmac.new(settings.secret_key.encode(), f"{purpose}:{user_id}:{code}".encode(), hashlib.sha256).hexdigest()


def _deliver(email: str, message: tuple[str, str, str]) -> None:
    """Send one message. Never raises: it runs after the response was already sent, so a failure is logged
    (without any code) and the person can simply ask again."""
    subject, text, page = message
    try:
        mailer.send_email(email, subject, text, page)
    except mailer.EmailError as e:
        logger.error("Could not email %s: %s", email, e)
    except Exception:  # noqa: BLE001 - a background task must not crash the worker
        logger.exception("Unexpected error while emailing %s", email)


def deliver_code(email: str, code: str) -> None:
    """Email the address-verification code."""
    _deliver(email, mailer.verification_email(code, settings.verification_code_ttl_minutes))


def deliver_reset_code(email: str, code: str) -> None:
    """Email the password-reset code."""
    _deliver(email, mailer.password_reset_email(code, settings.password_reset_code_ttl_minutes))


def deliver_password_changed(email: str) -> None:
    """Tell the owner their password changed, so a change they didn't make is noticed quickly."""
    _deliver(email, mailer.password_changed_email())


def issue_code(db: Session, user: User, now: datetime | None = None) -> str:
    """Create (or replace) the user's verification code and return it for delivery (the caller emails it)."""
    now = now or utcnow()
    record = db.get(EmailVerification, user.id)
    if record is not None:
        wait = settings.verification_resend_cooldown_seconds - (now - record.sent_at).total_seconds()
        if wait > 0:
            raise AccountError(f"Please wait {int(wait) + 1}s before requesting another code", "rate_limited")
    else:
        record = EmailVerification(user_id=user.id)
        db.add(record)

    code = f"{secrets.randbelow(10**6):06d}"
    record.code_hash = _hash_code(user.id, code)
    record.expires_at = now + timedelta(minutes=settings.verification_code_ttl_minutes)
    record.attempts = 0
    record.sent_at = now
    db.commit()
    return code


def verify_code(db: Session, user: User, code: str, now: datetime | None = None) -> None:
    now = now or utcnow()
    if user.is_verified:
        return  # already done; verifying twice is harmless
    record = db.get(EmailVerification, user.id)
    if record is None:
        raise AccountError("No code has been requested. Ask for a new one.")
    if now >= record.expires_at:
        raise AccountError("That code has expired. Ask for a new one.")
    if record.attempts >= settings.verification_max_attempts:
        raise AccountError("Too many wrong attempts. Ask for a new code.", "rate_limited")

    if not hmac.compare_digest(record.code_hash, _hash_code(user.id, code)):
        record.attempts += 1
        db.commit()
        left = settings.verification_max_attempts - record.attempts
        raise AccountError(f"Incorrect code. {left} attempt(s) left.")

    user.is_verified = True
    db.delete(record)
    db.commit()


# --- forgotten password -----------------------------------------------------

_INVALID_RESET = "That code is invalid or has expired. Request a new one."


def issue_reset_code(db: Session, user: User, now: datetime | None = None) -> str | None:
    """A fresh reset code, or None if one was sent a moment ago.

    It does not raise on the cooldown: the endpoint must answer exactly the same whether or not it sent anything,
    so the response can't be used to find out which emails have accounts.
    """
    now = now or utcnow()
    record = db.get(PasswordReset, user.id)
    if record is not None and (now - record.sent_at).total_seconds() < settings.verification_resend_cooldown_seconds:
        return None
    if record is None:
        record = PasswordReset(user_id=user.id)
        db.add(record)
    code = f"{secrets.randbelow(10**6):06d}"
    record.code_hash = _hash_code(user.id, code, "reset")
    record.expires_at = now + timedelta(minutes=settings.password_reset_code_ttl_minutes)
    record.attempts = 0
    record.sent_at = now
    db.commit()
    return code


def reset_password(db: Session, user: User, code: str, new_password: str, now: datetime | None = None) -> None:
    """Set a new password using an emailed code. Every failure that could hint at an account says the same thing."""
    now = now or utcnow()
    record = db.get(PasswordReset, user.id)
    if record is None or now >= record.expires_at:
        raise AccountError(_INVALID_RESET)
    if record.attempts >= settings.verification_max_attempts:
        raise AccountError("Too many wrong attempts. Request a new code.", "rate_limited")
    if not hmac.compare_digest(record.code_hash, _hash_code(user.id, code, "reset")):
        record.attempts += 1
        db.commit()
        raise AccountError(_INVALID_RESET)

    user.password_hash = hash_password(new_password)
    user.password_changed_at = now  # every older login token stops working
    user.is_verified = True  # they just proved they control this inbox
    db.delete(record)
    db.commit()
