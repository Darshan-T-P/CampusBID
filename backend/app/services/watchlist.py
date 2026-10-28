"""Saved auctions and "closing soon" reminders.

A buyer saves an auction; before it closes they get reminders (once per window), and when it ends
they are told how it turned out. People who bid, or set an automatic maximum, are reminded too:
they are just as interested. Notifications are ordinary persistent records, so a buyer who was
offline sees everything they missed in the bell later.
"""

import math
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.clock import utcnow
from app.models import AutoBid, Bid, ClosingReminder, Listing, ListingStatus, Watch
from app.schemas.listing import ListingCard
from app.services import notifications
from app.services.auction import begin_write, min_valid_bid
from app.services.errors import ListingError
from app.services.listings import _card

# Minutes before closing at which a reminder is due, longest first.
REMINDER_WINDOWS = (60, 5)
MAX_WATCHES = 200  # per person: a cap, so the list (and the reminder sweep) stays small


def _listing_or_404(db: Session, listing_id: int) -> Listing:
    listing = db.get(Listing, listing_id)
    if listing is None:
        raise ListingError("Listing not found", "not_found")
    return listing


def watch(db: Session, listing_id: int, user_id: int, now: datetime | None = None) -> None:
    """Save an auction. Saving twice is fine (it stays saved)."""
    now = now or utcnow()
    listing = _listing_or_404(db, listing_id)
    if listing.seller_id == user_id:
        raise ListingError("You can't save your own listing", "forbidden")
    if db.scalar(select(Watch.id).where(Watch.listing_id == listing_id, Watch.user_id == user_id)) is not None:
        return
    if listing.status != ListingStatus.active or now >= listing.closes_at:
        raise ListingError("This auction has ended, so there is nothing left to watch", "conflict")
    count = db.scalar(select(func.count()).select_from(Watch).where(Watch.user_id == user_id))
    if count >= MAX_WATCHES:
        raise ListingError(f"You can save up to {MAX_WATCHES} auctions. Remove some first.", "conflict")
    db.add(Watch(listing_id=listing_id, user_id=user_id, created_at=now))
    db.commit()


def unwatch(db: Session, listing_id: int, user_id: int) -> None:
    row = db.scalar(select(Watch).where(Watch.listing_id == listing_id, Watch.user_id == user_id))
    if row is not None:
        db.delete(row)
        db.commit()


def my_watchlist(db: Session, user_id: int) -> list[ListingCard]:
    """Saved auctions: open ones first (closing soonest at the top), then ended ones, most recent first."""
    bid_count = select(func.count()).where(Bid.listing_id == Listing.id).correlate(Listing).scalar_subquery()
    rows = db.execute(
        select(Listing, bid_count)
        .join(Watch, Watch.listing_id == Listing.id)
        .where(Watch.user_id == user_id)
        .options(selectinload(Listing.images), joinedload(Listing.seller))
    ).all()
    cards = [_card(listing, count) for listing, count in rows]
    open_ = sorted((c for c in cards if c.status == ListingStatus.active), key=lambda c: c.closes_at)
    ended = sorted((c for c in cards if c.status != ListingStatus.active), key=lambda c: c.closes_at, reverse=True)
    return open_ + ended


def watcher_ids(db: Session, listing_id: int) -> set[int]:
    return set(db.scalars(select(Watch.user_id).where(Watch.listing_id == listing_id)).all())


# --- reminders ---------------------------------------------------------------


def _left(remaining: timedelta) -> str:
    minutes = max(1, math.ceil(remaining.total_seconds() / 60))
    if minutes >= 55:
        return "about an hour"
    return f"{minutes} minute{'s' if minutes != 1 else ''}"


def _interested(db: Session, listing: Listing) -> set[int]:
    people = watcher_ids(db, listing.id)
    people |= set(db.scalars(select(Bid.bidder_id).where(Bid.listing_id == listing.id)).all())
    people |= set(db.scalars(select(AutoBid.user_id).where(AutoBid.listing_id == listing.id)).all())
    people.discard(listing.seller_id)
    return people


def _remind(db: Session, listing: Listing, user_id: int, leader: int | None, remaining: timedelta, now: datetime) -> None:
    price = listing.current_price if listing.current_price is not None else listing.starting_price
    left = _left(remaining)
    if user_id == leader:
        title = f"{listing.title} closes in {left}"
        body = f"You're leading at ₹{price}. You win unless someone bids higher."
    elif db.scalar(select(Bid.id).where(Bid.listing_id == listing.id, Bid.bidder_id == user_id).limit(1)) is not None:
        title = f"{listing.title} closes in {left}"
        body = f"You're not leading. It's at ₹{price}; the next bid must be at least ₹{min_valid_bid(listing)}."
    else:
        title = f"{listing.title} closes in {left}"
        body = f"Currently ₹{price}. Bid before it ends{'' if listing.current_price is not None else ' (no bids yet)'}."
    notifications.notify(db, user_id, "reminder", title, body, listing.id, now=now)


def has_reminders_due(db: Session, now: datetime) -> bool:
    horizon = now + timedelta(minutes=max(REMINDER_WINDOWS))
    return (
        db.scalar(
            select(Listing.id)
            .where(Listing.status == ListingStatus.active, Listing.closes_at > now, Listing.closes_at <= horizon)
            .limit(1)
        )
        is not None
    )


def send_due_reminders(db: Session, now: datetime | None = None) -> int:
    """Send every reminder that is due and not yet sent. Returns how many notifications were queued.

    Each person gets at most one reminder per sweep for an auction: the one for the smallest window that
    applies (someone who saves an auction with 20 minutes left hears "closes in 20 minutes", not two messages),
    and every larger window is marked as handled so it never fires later. Runs under the write lock, and the
    record of what was sent commits together with the notification, so a reminder goes out exactly once.
    """
    now = now or utcnow()
    if not has_reminders_due(db, now):
        return 0
    horizon = now + timedelta(minutes=max(REMINDER_WINDOWS))
    queued = 0
    begin_write(db)
    try:
        listings = db.scalars(
            select(Listing)
            .where(Listing.status == ListingStatus.active, Listing.closes_at > now, Listing.closes_at <= horizon)
            .execution_options(populate_existing=True)
        ).all()
        for listing in listings:
            remaining = listing.closes_at - now
            applicable = [w for w in REMINDER_WINDOWS if remaining <= timedelta(minutes=w)]
            leader = notifications.winner_id(db, listing)
            for user_id in _interested(db, listing):
                done = set(
                    db.scalars(
                        select(ClosingReminder.window_minutes).where(
                            ClosingReminder.listing_id == listing.id, ClosingReminder.user_id == user_id
                        )
                    ).all()
                )
                if min(applicable) in done:
                    continue
                for window in applicable:
                    if window not in done:
                        db.add(ClosingReminder(listing_id=listing.id, user_id=user_id, window_minutes=window, sent_at=now))
                _remind(db, listing, user_id, leader, remaining, now)
                queued += 1
        db.commit()
        return queued
    except BaseException:
        db.rollback()
        raise
