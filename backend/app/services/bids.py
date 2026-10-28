from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Bid
from app.schemas.bid import BidPublic


def to_public(bid: Bid) -> BidPublic:
    return BidPublic(
        id=bid.id,
        amount=bid.amount,
        bidder_name=bid.bidder.display_name,
        created_at=bid.created_at,
        is_auto=bid.is_auto,
    )


def bid_history(db: Session, listing_id: int) -> list[BidPublic]:
    """Every bid on a listing, newest (= highest) first."""
    bids = db.scalars(
        select(Bid)
        .where(Bid.listing_id == listing_id)
        .order_by(Bid.id.desc())
        .options(joinedload(Bid.bidder))
    ).all()
    return [to_public(b) for b in bids]
