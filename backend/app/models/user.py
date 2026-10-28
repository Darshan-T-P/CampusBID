from datetime import datetime

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utcnow
from app.db.session import Base
from app.db.types import UTCDateTime


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(80))
    # Who they are on campus. Shown next to a seller's name, never alongside their email.
    department: Mapped[str | None] = mapped_column(String(80), default=None)
    year_of_study: Mapped[int | None] = mapped_column(Integer, default=None)  # 1-5, or 6 for postgraduate
    # Only verified campus emails may list or bid; unverified accounts can browse.
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    # Login tokens issued before this moment are refused, so changing the password signs out other devices.
    password_changed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    # Set when the person deletes their account (the row stays only to keep other students' histories intact).
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
