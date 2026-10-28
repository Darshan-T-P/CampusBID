from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utcnow
from app.db.session import Base
from app.db.types import UTCDateTime
from app.models.listing import Category


class Want(Base):
    """A saved search: "tell me when a cycle under ₹2,000 is listed". Kept on the server, so a match is never lost
    if the student was offline when it was posted."""

    __tablename__ = "wants"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    keywords: Mapped[str] = mapped_column(String(80), default="")  # every word must appear in the title or description
    category: Mapped[Category | None] = mapped_column(Enum(Category), default=None)
    max_price: Mapped[int | None] = mapped_column(Integer, default=None)  # compared with the listing's starting price
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
