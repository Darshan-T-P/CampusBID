"""Campus-only trust: who may register, and proving they own the email they gave."""

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.config import settings
from app.models import EmailVerification, User
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
    if not domain_allowed(email):
        raise AccountError("Please use your campus email address")
    return email


# --- verification codes -----------------------------------------------------


def _hash_code(user_id: int, code: str) -> str:
    # Keyed hash: a leaked database row can't be reversed into a code without the secret.
    return hmac.new(settings.secret_key.encode(), f"{user_id}:{code}".encode(), hashlib.sha256).hexdigest()


def deliver_code(email: str, code: str) -> None:
    """Hand the code to the user. There is no email transport yet.

    In dev/demo mode the code is printed to the server log so anyone can try the flow.
    A real deployment would send an email here.
    """
    if settings.dev_mode:
        logger.warning("[DEV] Verification code for %s: %s", email, code)
    else:
        logger.warning("No email transport configured; could not send a code to %s", email)


def issue_code(db: Session, user: User, now: datetime | None = None) -> None:
    """Create (or replace) the user's verification code and deliver it."""
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
    deliver_code(user.email, code)


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
