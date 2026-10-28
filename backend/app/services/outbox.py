"""Queueing and delivering the emails about how auctions and sales turn out.

`queue_email` only adds a row, so it belongs inside the caller's transaction (see models/outbox.py). `send_pending`
runs in its own loop (services/closer.py) and delivers what is waiting.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.models import OutboxEmail, User
from app.services import mailer

logger = logging.getLogger("campusbid.outbox")

MAX_ATTEMPTS = 5


def wants_email(user: User | None) -> bool:
    """Real, current, opted-in recipients only (never a deleted account's placeholder address)."""
    return user is not None and user.notify_by_email and user.deleted_at is None and not user.email.endswith(".invalid")


def queue_email(db: Session, user: User | None, message: tuple[str, str, str], now: datetime | None = None) -> OutboxEmail | None:
    """Queue (subject, text, html) for `user`. Adds to the open transaction; does not commit or send."""
    if not wants_email(user):
        return None
    subject, text, page = message
    now = now or utcnow()
    row = OutboxEmail(to_email=user.email, subject=subject[:255], body_text=text, body_html=page, created_at=now, next_try_at=now)
    db.add(row)
    return row


def _due(now: datetime):
    return (OutboxEmail.sent_at.is_(None), OutboxEmail.attempts < MAX_ATTEMPTS, OutboxEmail.next_try_at <= now)


def has_pending(db: Session, now: datetime | None = None) -> bool:
    return db.scalar(select(OutboxEmail.id).where(*_due(now or utcnow())).limit(1)) is not None


def send_pending(db: Session, now: datetime | None = None, limit: int = 20) -> tuple[int, int]:
    """Deliver due emails. Returns (sent, failed). A failure is retried later (2, 4, 8, 16 minutes), then given up on."""
    now = now or utcnow()
    sent = failed = 0
    rows = db.scalars(select(OutboxEmail).where(*_due(now)).order_by(OutboxEmail.id).limit(limit)).all()
    for row in rows:
        try:
            mailer.send_email(row.to_email, row.subject, row.body_text, row.body_html)
        except mailer.EmailError as e:
            row.attempts += 1
            row.last_error = str(e)[:300]
            row.next_try_at = now + timedelta(minutes=2**row.attempts)
            failed += 1
            logger.error("Could not send email %s to %s (attempt %s): %s", row.id, row.to_email, row.attempts, e)
        except ValueError as e:  # a malformed address or header: retrying will never help
            row.attempts = MAX_ATTEMPTS
            row.last_error = str(e)[:300]
            failed += 1
            logger.error("Email %s to %s can't be sent and will not be retried: %s", row.id, row.to_email, e)
        else:
            row.sent_at = now
            row.last_error = None
            sent += 1
        db.commit()  # one row at a time: a crash later never causes an earlier email to be sent again
    return sent, failed
