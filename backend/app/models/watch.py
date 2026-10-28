from datetime import datetime

from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utcnow
from app.db.session import Base
from app.db.types import UTCDateTime


class Watch(Base):
    """A buyer's saved auction: "tell me before this closes and when it ends". One per buyer per auction."""

    __tablename__ = "watches"
    __table_args__ = (UniqueConstraint("listing_id", "user_id", name="uq_watch_listing_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ClosingReminder(Base):
    """Remembers which "closing soon" reminders were already sent, so each one goes out once per person."""

    __tablename__ = "closing_reminders"
    __table_args__ = (UniqueConstraint("listing_id", "user_id", "window_minutes", name="uq_reminder_once"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    window_minutes: Mapped[int] = mapped_column(Integer)
    sent_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
