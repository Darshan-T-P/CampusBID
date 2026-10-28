import enum
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import utcnow
from app.db.session import Base
from app.db.types import UTCDateTime


class Category(str, enum.Enum):
    cycle = "cycle"
    calculator = "calculator"
    books = "books"
    electronics = "electronics"
    furniture = "furniture"
    other = "other"


class Condition(str, enum.Enum):
    new = "new"
    like_new = "like_new"
    good = "good"
    fair = "fair"
    poor = "poor"


class ListingStatus(str, enum.Enum):
    active = "active"
    pending_approval = "pending_approval"  # closed with a bid; seller must approve
    reserved = "reserved"  # approved; awaiting handover
    completed = "completed"
    failed_pickup = "failed_pickup"
    rejected = "rejected"
    unsold = "unsold"  # closed with no bids
    cancelled = "cancelled"


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    category: Mapped[Category] = mapped_column(Enum(Category), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    condition: Mapped[Condition] = mapped_column(Enum(Condition))
    # Money is whole rupees (integers); never floats.
    starting_price: Mapped[int] = mapped_column(Integer)
    min_increment: Mapped[int] = mapped_column(Integer, default=1)
    closes_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    status: Mapped[ListingStatus] = mapped_column(
        Enum(ListingStatus), default=ListingStatus.active, index=True
    )
    current_price: Mapped[int | None] = mapped_column(Integer, default=None)
    # Plain column (no FK): listings and bids reference each other, and SQLite
    # cannot add the constraint after the fact.
    leading_bid_id: Mapped[int | None] = mapped_column(Integer, default=None)
    outcome_note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    seller = relationship("User")
    images: Mapped[list["ListingImage"]] = relationship(
        back_populates="listing", order_by="ListingImage.position", cascade="all, delete-orphan"
    )
    bids = relationship("Bid", back_populates="listing", order_by="Bid.id")


class ListingImage(Base):
    __tablename__ = "listing_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    path: Mapped[str] = mapped_column(String(255))
    position: Mapped[int] = mapped_column(Integer, default=0)

    listing: Mapped[Listing] = relationship(back_populates="images")
