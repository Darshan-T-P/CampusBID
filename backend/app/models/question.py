from datetime import datetime

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import utcnow
from app.db.session import Base
from app.db.types import UTCDateTime


class ListingQuestion(Base):
    """Public question and answer thread on a listing.

    Allows prospective student buyers to ask condition or detail questions
    (e.g., 'Do the gears shift well?') and allows the seller to reply publicly once,
    avoiding duplicate questions and spam.
    """

    __tablename__ = "listing_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    asker_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    question_text: Mapped[str] = mapped_column(Text)
    answer_text: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    answered_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)

    asker: Mapped["User"] = relationship(foreign_keys=[asker_id])
    listing: Mapped["Listing"] = relationship(foreign_keys=[listing_id])
