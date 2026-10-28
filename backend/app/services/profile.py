"""A person's own numbers: what they are selling and what they are bidding on."""

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.models import AutoBid, Bid, Listing, ListingStatus
from app.schemas.profile import BuyingSummary, ProfileSummary, SellingSummary
from app.services import notifications

S = ListingStatus


def build_summary(db: Session, user_id: int) -> ProfileSummary:
    by_status = dict(
        db.execute(
            select(Listing.status, func.count()).where(Listing.seller_id == user_id).group_by(Listing.status)
        ).all()
    )
    count = lambda *statuses: sum(by_status.get(s, 0) for s in statuses)  # noqa: E731
    earned = db.scalar(
        select(func.coalesce(func.sum(Listing.current_price), 0)).where(
            Listing.seller_id == user_id, Listing.status == S.completed
        )
    )
    selling = SellingSummary(
        total=sum(by_status.values()),
        open=count(S.active),
        awaiting_decision=count(S.pending_approval),
        awaiting_handover=count(S.reserved),
        sold=count(S.completed),
        unsold=count(S.unsold),
        other=count(S.cancelled, S.rejected, S.failed_pickup),
        earned=earned,
    )

    auctions = db.scalar(select(func.count(distinct(Bid.listing_id))).where(Bid.bidder_id == user_id))
    open_bid_on = db.scalar(
        select(func.count(distinct(Bid.listing_id)))
        .join(Listing, Listing.id == Bid.listing_id)
        .where(Bid.bidder_id == user_id, Listing.status == S.active)
    )
    # Auctions where MY bid is the one the listing currently points at (the leader while it runs, the winner once it ends).
    led = db.execute(
        select(Listing.status, Listing.current_price)
        .join(Bid, Bid.id == Listing.leading_bid_id)
        .where(Bid.bidder_id == user_id)
    ).all()
    leading = sum(1 for status, _ in led if status == S.active)
    won = sum(1 for status, _ in led if status in (S.pending_approval, S.reserved, S.completed))
    spent = sum(price or 0 for status, price in led if status == S.completed)
    buying = BuyingSummary(
        auctions=auctions,
        open=open_bid_on,
        leading=leading,
        outbid=open_bid_on - leading,
        won=won,
        spent=spent,
        bids_placed=db.scalar(select(func.count()).select_from(Bid).where(Bid.bidder_id == user_id)),
        automatic_maximums=db.scalar(
            select(func.count())
            .select_from(AutoBid)
            .join(Listing, Listing.id == AutoBid.listing_id)
            .where(AutoBid.user_id == user_id, Listing.status == S.active)
        ),
    )
    return ProfileSummary(selling=selling, buying=buying, unread_notifications=notifications.unread_count(db, user_id))
