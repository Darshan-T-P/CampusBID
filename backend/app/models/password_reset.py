from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utcnow
from app.db.session import Base
from app.db.types import UTCDateTime


class PasswordReset(Base):
    """The one outstanding "forgot my password" code for a user. Like verification codes, only a keyed hash is kept."""

    __tablename__ = "password_resets"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
