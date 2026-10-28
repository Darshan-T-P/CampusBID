from datetime import datetime

from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import utcnow
from app.db.session import Base
from app.db.types import UTCDateTime


class AutoBid(Base):
    """A bidder's standing instruction: "bid for me on this auction, as little as needed, up to this much".

    Maximums are public by design (the brief: nothing about bidding is private), so every field here
    may be shown to anyone. One per bidder per auction.
    """

    __tablename__ = "auto_bids"
    __table_args__ = (UniqueConstraint("listing_id", "user_id", name="uq_auto_bid_listing_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    max_amount: Mapped[int] = mapped_column(Integer)
    # When this ceiling was committed to. On a tie between two maximums, the earlier commitment wins;
    # changing your maximum resets it, so nobody can bank an early slot with a low number.
    set_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    user = relationship("User")
