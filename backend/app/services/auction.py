"""The auction engine: every money/time rule lives here.

Routes, the background closer and the auto-bidder all go through these
functions. `now` is injectable so tests control the clock; production passes nothing
and gets server time.
"""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.models import AutoBid, Bid, Listing, ListingStatus
from app.services import notifications
from app.services.errors import ListingError


# Anti-sniping: a valid bid in the last EXTENSION_WINDOW moves the closing time to EXTENSION_TO after that bid,
# so nobody can win by bidding a split second before the end and leaving no time to answer.
EXTENSION_WINDOW = timedelta(seconds=30)
EXTENSION_TO = timedelta(seconds=60)


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


def close_if_due(db: Session, listing: Listing, now: datetime) -> bool:
    """Move an active listing past its closing time to its closed state.

    Highest bid -> pending_approval (winner is provisional until the seller approves);
    no bids -> unsold. Queues the "won / ended / unsold" notifications. Returns True if the
    listing changed. The caller holds the write lock and commits, which is what guarantees
    each listing is closed (and announced) exactly once.
    """
    if listing.status != ListingStatus.active or now < listing.closes_at:
        return False
    if listing.leading_bid_id is not None:
        listing.status = ListingStatus.pending_approval
        listing.outcome_note = f"Closed with a winning bid of {listing.current_price}"
    else:
        listing.status = ListingStatus.unsold
        listing.outcome_note = "Closed with no bids"
    notifications.auction_closed(db, listing, now)
    return True


def ensure_closed(db: Session, listing: Listing, now: datetime | None = None) -> None:
    """Lazy close for reads: if the listing is past its time, close it now.

    The cheap check runs first so ordinary reads never take the write lock. When the listing
    is overdue we lock, re-read, and re-check: if another request closed it meanwhile this
    does nothing, so notifications are never sent twice.
    """
    now = now or utcnow()
    if listing.status != ListingStatus.active or now < listing.closes_at:
        return
    begin_write(db)
    try:
        fresh = db.scalars(
            select(Listing).where(Listing.id == listing.id).execution_options(populate_existing=True)
        ).one()
        close_if_due(db, fresh, now)
        db.commit()
    except BaseException:
        db.rollback()
        raise


def begin_write(db: Session) -> None:
    """Take SQLite's write lock up front (BEGIN IMMEDIATE).

    Without it two racing bids can both read the same current price, both pass the
    increment check, and both insert. Holding the write lock across read-validate-write
    serializes them. Must run before the session's first statement.
    """
    if db.get_bind().dialect.name == "sqlite":
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")


def _extend_if_late(listing: Listing, now: datetime) -> None:
    """If this bid landed in the final seconds, push the closing time to EXTENSION_TO after it.

    Runs for every bid, so automatic bids extend too; several bids at the same instant (a manual bid and the
    automatic answers it triggers) all land on the same new closing time, which counts as one extension.
    The caller holds the write lock, so the closer can never close the auction between the bid and this.
    """
    if listing.closes_at - now <= EXTENSION_WINDOW:
        new_close = now + EXTENSION_TO
        if new_close > listing.closes_at:
            listing.closes_at = new_close
            listing.extension_count += 1


def _insert_bid(db: Session, listing: Listing, bidder_id: int, amount: int, now: datetime, is_auto: bool) -> Bid:
    """Record a bid and move the listing's price and leader. The one place a bid row is ever created."""
    previous_leader = notifications.winner_id(db, listing)  # read before the lead changes
    bid = Bid(listing_id=listing.id, bidder_id=bidder_id, amount=amount, created_at=now, is_auto=is_auto)
    db.add(bid)
    db.flush()
    listing.current_price = amount
    listing.leading_bid_id = bid.id
    _extend_if_late(listing, now)
    notifications.bid_placed(db, listing, bid, previous_leader)
    return bid


def _resolve_auto_bids(db: Session, listing: Listing, now: datetime) -> None:
    """Let standing maximums respond until nobody left could still validly beat the current price.

    Each round takes the strongest challenger (highest maximum; on a tie, whoever committed first) and
    settles it against the current leader, whose "ceiling" is the higher of their price and their own
    maximum:

    * challenger above the ceiling  -> challenger leads, one step over the ceiling (never past their maximum)
    * leader at or above it         -> the challenger bids as high as the leader can still answer, and the
                                       leader's own maximum answers one step higher
    * challenger cannot afford a valid bid -> they are skipped this round

    Every bid made this way clears the normal increment rule, so the history reads like real bidding.
    Runs inside the caller's write lock, so it can't race with anyone.
    """
    step = listing.min_increment
    skipped: set[int] = set()
    for _ in range(500):  # each round raises the price or retires a challenger; this is only a safety net
        leader_id = notifications.winner_id(db, listing)
        autos = db.scalars(select(AutoBid).where(AutoBid.listing_id == listing.id)).all()
        needed = min_valid_bid(listing)
        challengers = [a for a in autos if a.user_id != leader_id and a.max_amount >= needed and a.id not in skipped]
        if not challengers:
            return
        challenger = min(challengers, key=lambda a: (-a.max_amount, a.set_at, a.id))
        if leader_id is None:  # nobody has bid yet: the strongest maximum opens at the starting price
            _insert_bid(db, listing, challenger.user_id, needed, now, is_auto=True)
            continue

        leader_auto = next((a for a in autos if a.user_id == leader_id), None)
        ceiling = max(listing.current_price, leader_auto.max_amount) if leader_auto else listing.current_price
        challenger_committed_first = (
            leader_auto is not None
            and leader_auto.max_amount == ceiling
            and (challenger.set_at, challenger.id) < (leader_auto.set_at, leader_auto.id)
        )
        if challenger.max_amount > ceiling or (challenger.max_amount == ceiling and challenger_committed_first):
            _insert_bid(db, listing, challenger.user_id, min(challenger.max_amount, ceiling + step), now, is_auto=True)
        else:
            highest = min(challenger.max_amount, ceiling - step)  # the most the leader can still answer
            if highest < needed:
                skipped.add(challenger.id)
                continue
            _insert_bid(db, listing, challenger.user_id, highest, now, is_auto=True)
            _insert_bid(db, listing, leader_id, highest + step, now, is_auto=True)
    raise RuntimeError("automatic bidding did not settle")


def set_auto_bid(
    db: Session, listing_id: int, user_id: int, max_amount: int, now: datetime | None = None
) -> AutoBid:
    """Set or change my maximum on an auction. The app then bids for me, as little as needed, up to it."""
    now = now or utcnow()
    begin_write(db)
    try:
        listing = db.scalars(
            select(Listing).where(Listing.id == listing_id).execution_options(populate_existing=True)
        ).one_or_none()
        if listing is None:
            raise BidError("not_found", "Listing not found")
        if close_if_due(db, listing, now):
            db.commit()
            raise BidError("closed", "Auction has closed")
        if listing.status != ListingStatus.active:
            raise BidError("closed", "Auction is not open for bids")
        if user_id == listing.seller_id:
            raise BidError("own_listing", "You cannot bid on your own listing")

        leading = notifications.winner_id(db, listing) == user_id
        floor = listing.current_price if leading else min_valid_bid(listing)  # a leader only needs to cover their own price
        if max_amount < floor:
            raise BidError("too_low", f"Your maximum must be at least {floor}", min_bid=floor)

        auto = db.scalar(select(AutoBid).where(AutoBid.listing_id == listing.id, AutoBid.user_id == user_id))
        if auto is None:
            auto = AutoBid(listing_id=listing.id, user_id=user_id, max_amount=max_amount, set_at=now)
            db.add(auto)
        elif auto.max_amount != max_amount:
            auto.max_amount = max_amount
            auto.set_at = now  # a new commitment goes to the back of the queue on ties
        db.flush()
        _resolve_auto_bids(db, listing, now)
        db.commit()
        return auto
    except BaseException:
        db.rollback()
        raise


def remove_auto_bid(db: Session, listing_id: int, user_id: int, now: datetime | None = None) -> None:
    """Withdraw my maximum. Bids already placed stand; nothing more will be placed for me."""
    now = now or utcnow()
    begin_write(db)
    try:
        listing = db.scalars(
            select(Listing).where(Listing.id == listing_id).execution_options(populate_existing=True)
        ).one_or_none()
        if listing is None:
            raise BidError("not_found", "Listing not found")
        if close_if_due(db, listing, now):
            db.commit()
            raise BidError("closed", "Auction has closed")
        if listing.status != ListingStatus.active:
            raise BidError("closed", "Auction is not open for bids")
        auto = db.scalar(select(AutoBid).where(AutoBid.listing_id == listing.id, AutoBid.user_id == user_id))
        if auto is None:
            raise BidError("not_found", "You have no maximum set on this auction")
        db.delete(auto)
        db.commit()
    except BaseException:
        db.rollback()
        raise


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
        if close_if_due(db, listing, now):
            db.commit()
            raise BidError("closed", "Auction has closed")
        if listing.status != ListingStatus.active:
            raise BidError("closed", "Auction is not open for bids")
        if bidder_id == listing.seller_id:
            raise BidError("own_listing", "You cannot bid on your own listing")
        previous_leader = notifications.winner_id(db, listing)
        if previous_leader == bidder_id:
            raise BidError("already_leading", "You already have the highest bid")
        minimum = min_valid_bid(listing)
        if amount < minimum:
            raise BidError("too_low", f"Bid must be at least {minimum}", min_bid=minimum)

        bid = _insert_bid(db, listing, bidder_id, amount, now, is_auto=False)
        _resolve_auto_bids(db, listing, now)  # standing automatic bids may answer this one at once
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
        if close_if_due(db, listing, now):
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
        notifications.listing_cancelled(db, listing, actor_id=user_id)
        db.commit()
        return listing
    except BaseException:
        db.rollback()
        raise


def has_due_listings(db: Session, now: datetime | None = None) -> bool:
    """Cheap read-only check (no write lock) so an idle sweep never blocks real bids."""
    now = now or utcnow()
    due = db.scalar(
        select(Listing.id)
        .where(Listing.status == ListingStatus.active, Listing.closes_at <= now)
        .limit(1)
    )
    return due is not None


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
        closed = [listing for listing in due if close_if_due(db, listing, now)]
        db.commit()
        return closed
    except BaseException:
        db.rollback()
        raise
