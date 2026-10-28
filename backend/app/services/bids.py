from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import AutoBid, Bid
from app.schemas.bid import AutoBidPublic, BidPublic


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


def auto_bid_to_public(auto: AutoBid) -> AutoBidPublic:
    return AutoBidPublic(bidder_name=auto.user.display_name, max_amount=auto.max_amount, set_at=auto.set_at)


def list_auto_bids(db: Session, listing_id: int) -> list[AutoBidPublic]:
    """Every standing maximum on an auction, highest first. Public."""
    autos = db.scalars(
        select(AutoBid)
        .where(AutoBid.listing_id == listing_id)
        .order_by(AutoBid.max_amount.desc(), AutoBid.set_at, AutoBid.id)
        .options(joinedload(AutoBid.user))
    ).all()
    return [auto_bid_to_public(a) for a in autos]
