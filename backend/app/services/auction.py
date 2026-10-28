"""The auction engine: every money/time rule lives here.

Routes, the background closer and (later) the auto-bidder all go through these
functions. `now` is injectable so tests control the clock; production passes nothing
and gets server time.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.models import Bid, Listing, ListingStatus
from app.services.errors import ListingError


class BidError(Exception):
    """A bid was refused. `code` is machine-readable; `min_bid` is set for `too_low`."""

    def __init__(self, code: str, message: str, min_bid: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.min_bid = min_bid


def min_valid_bid(listing: Listing) -> int:
    if listing.current_price is None:
        return listing.starting_price
    return listing.current_price + listing.min_increment


def close_if_due(listing: Listing, now: datetime) -> bool:
    """Move an active listing past its closing time to its closed state.

    Highest bid -> pending_approval (winner is provisional until the seller approves);
    no bids -> unsold. Returns True if the listing changed. Caller commits.
    """
    if listing.status != ListingStatus.active or now < listing.closes_at:
        return False
    if listing.leading_bid_id is not None:
        listing.status = ListingStatus.pending_approval
        listing.outcome_note = f"Closed with a winning bid of {listing.current_price}"
    else:
        listing.status = ListingStatus.unsold
        listing.outcome_note = "Closed with no bids"
    return True


def ensure_closed(db: Session, listing: Listing, now: datetime | None = None) -> None:
    """Lazy close for reads: if the listing is past its time, persist the closed state.

    Idempotent, so two readers racing to do it is harmless.
    """
    if close_if_due(listing, now or utcnow()):
        db.commit()


def begin_write(db: Session) -> None:
    """Take SQLite's write lock up front (BEGIN IMMEDIATE).

    Without it two racing bids can both read the same current price, both pass the
    increment check, and both insert. Holding the write lock across read-validate-write
    serializes them. Must run before the session's first statement.
    """
    if db.get_bind().dialect.name == "sqlite":
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")


def place_bid(
    db: Session,
    listing_id: int,
    bidder_id: int,
    amount: int,
    now: datetime | None = None,
) -> Bid:
    """The single entry point for placing a bid. Commits on success; raises BidError."""
    now = now or utcnow()
    begin_write(db)
    try:
        listing = db.scalars(
            select(Listing).where(Listing.id == listing_id).execution_options(populate_existing=True)
        ).one_or_none()
        if listing is None:
            raise BidError("not_found", "Listing not found")

        # Lazy close: a stale background sweep must never let a late bid through.
        if close_if_due(listing, now):
            db.commit()
            raise BidError("closed", "Auction has closed")
        if listing.status != ListingStatus.active:
            raise BidError("closed", "Auction is not open for bids")
        if bidder_id == listing.seller_id:
            raise BidError("own_listing", "You cannot bid on your own listing")
        minimum = min_valid_bid(listing)
        if amount < minimum:
            raise BidError("too_low", f"Bid must be at least {minimum}", min_bid=minimum)

        bid = Bid(listing_id=listing.id, bidder_id=bidder_id, amount=amount, created_at=now)
        db.add(bid)
        db.flush()
        listing.current_price = amount
        listing.leading_bid_id = bid.id
        db.commit()
        return bid
    except BaseException:
        db.rollback()
        raise


def lock_listing_for_seller(
    db: Session, listing_id: int, user_id: int, now: datetime | None = None
) -> Listing:
    """Start a seller action (edit, cancel, photo change) on an active listing.

    Takes the write lock first, so the action is serialized with incoming bids: a bid can't
    slip in between "there are no bids yet" being checked and the change being saved.
    On success the lock is still held; the caller must commit or roll back.
    """
    now = now or utcnow()
    begin_write(db)
    try:
        listing = db.scalars(
            select(Listing).where(Listing.id == listing_id).execution_options(populate_existing=True)
        ).one_or_none()
        if listing is None:
            raise ListingError("Listing not found", "not_found")
        if listing.seller_id != user_id:
            raise ListingError("Only the seller can do that", "forbidden")
        if close_if_due(listing, now):
            db.commit()
            raise ListingError("This auction has already closed", "conflict")
        if listing.status != ListingStatus.active:
            raise ListingError(f"Listing is {listing.status.value}, not active", "conflict")
        return listing
    except BaseException:
        db.rollback()
        raise


def cancel_listing(db: Session, listing_id: int, user_id: int, now: datetime | None = None) -> Listing:
    """Seller withdraws an active listing, even if it already has bids."""
    listing = lock_listing_for_seller(db, listing_id, user_id, now)
    try:
        listing.status = ListingStatus.cancelled
        listing.outcome_note = "Cancelled by the seller"
        db.commit()
        return listing
    except BaseException:
        db.rollback()
        raise


def close_due_listings(db: Session, now: datetime | None = None) -> list[Listing]:
    """Sweep: close every active listing whose time has passed. Used by the background task."""
    now = now or utcnow()
    begin_write(db)
    try:
        due = db.scalars(
            select(Listing)
            .where(Listing.status == ListingStatus.active, Listing.closes_at <= now)
            .execution_options(populate_existing=True)
        ).all()
        closed = [listing for listing in due if close_if_due(listing, now)]
        db.commit()
        return closed
    except BaseException:
        db.rollback()
        raise
