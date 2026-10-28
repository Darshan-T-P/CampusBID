"""Creating and reading notifications.

Writers here only `db.add()`: the caller's transaction commits the notification together
with the event that caused it (a bid, a close, a status change), so the two can never
disagree. All wording lives in this file.
"""

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.config import settings
from app.models import Bid, Listing, Notification, User, Watch
from app.services import mailer, outbox


def notify(
    db: Session,
    user_id: int,
    type: str,
    title: str,
    body: str = "",
    listing_id: int | None = None,
    *,
    actor_id: int | None = None,
    now: datetime | None = None,
) -> Notification | None:
    """Queue a notification for `user_id`. Never notifies the person who caused the event."""
    if user_id == actor_id:
        return None
    note = Notification(
        user_id=user_id,
        type=type,
        title=title,
        body=body,
        listing_id=listing_id,
        created_at=now or utcnow(),
    )
    db.add(note)
    return note


def winner_id(db: Session, listing: Listing) -> int | None:
    if listing.leading_bid_id is None:
        return None
    return db.scalar(select(Bid.bidder_id).where(Bid.id == listing.leading_bid_id))


# --- event helpers: one per thing that happens in the auction ---------------


def bid_placed(db: Session, listing: Listing, bid: Bid, previous_leader_id: int | None) -> None:
    bidder_name = db.scalar(select(User.display_name).where(User.id == bid.bidder_id))
    if previous_leader_id is not None:
        notify(
            db, previous_leader_id, "outbid", f"You were outbid on {listing.title}",
            f"The price is now ₹{bid.amount}. Place a higher bid or raise your maximum to get back in.",
            listing.id, actor_id=bid.bidder_id, now=bid.created_at,
        )
    notify(
        db, listing.seller_id, "new_bid", f"New bid on {listing.title}",
        f"{bidder_name} bid ₹{bid.amount}{' (automatic bid)' if bid.is_auto else ''}.",
        listing.id, actor_id=bid.bidder_id, now=bid.created_at,
    )


def _followers(db: Session, listing: Listing) -> tuple[set[int], set[int]]:
    """(people who bid, people who only saved the auction), never the seller."""
    bidders = set(db.scalars(select(Bid.bidder_id).where(Bid.listing_id == listing.id)).all())
    watchers = set(db.scalars(select(Watch.user_id).where(Watch.listing_id == listing.id)).all()) - bidders
    bidders.discard(listing.seller_id)
    watchers.discard(listing.seller_id)
    return bidders, watchers


def auction_closed(db: Session, listing: Listing, now: datetime) -> None:
    """Called exactly once, at the moment a listing leaves `active` by running out of time."""
    winner = winner_id(db, listing)
    bidders, watchers = _followers(db, listing)
    for user_id in bidders - {winner}:
        notify(
            db, user_id, "lost", f"You didn't win {listing.title}",
            f"It ended at ₹{listing.current_price}, above your highest bid.", listing.id, now=now,
        )
    for user_id in watchers:
        result = f"It ended at ₹{listing.current_price}." if winner is not None else "It ended with no bids."
        notify(db, user_id, "watch_ended", f"{listing.title} has ended", f"An auction you saved is over. {result}", listing.id, now=now)
    if winner is None:
        notify(
            db, listing.seller_id, "unsold", f"{listing.title} ended with no bids",
            "Nobody bid, so it was not sold. You can list it again.", listing.id, now=now,
        )
        return
    winner_name = db.scalar(select(User.display_name).where(User.id == winner))
    # The emails that matter: the winner is told what they won and for how much; the seller is asked to decide.
    url = f"{settings.public_url.rstrip('/')}/listings/{listing.id}"
    seller = db.get(User, listing.seller_id)
    outbox.queue_email(
        db, db.get(User, winner),
        mailer.auction_won_email(listing.title, listing.current_price, seller.display_name, listing.handover_spot, url), now,
    )
    outbox.queue_email(db, seller, mailer.auction_ended_seller_email(listing.title, listing.current_price, winner_name, url), now)
    notify(
        db, winner, "won", f"You won {listing.title}",
        f"Your bid of ₹{listing.current_price} is the highest. It's provisional until the seller approves.",
        listing.id, now=now,
    )
    notify(
        db, listing.seller_id, "auction_ended", f"{listing.title} has ended",
        f"Top bid: ₹{listing.current_price} by {winner_name}. Approve or reject the sale.",
        listing.id, now=now,
    )


def listing_cancelled(db: Session, listing: Listing, actor_id: int) -> None:
    bidders, watchers = _followers(db, listing)
    for bidder in bidders:
        notify(
            db, bidder, "cancelled", f"{listing.title} was cancelled",
            "The seller withdrew this listing, so your bid no longer applies.", listing.id, actor_id=actor_id,
        )
    for watcher in watchers:
        notify(
            db, watcher, "cancelled", f"{listing.title} was cancelled",
            "The seller withdrew an auction you saved.", listing.id, actor_id=actor_id,
        )


def sale_step(db: Session, listing: Listing, actor_id: int, type: str, title: str, body: str) -> None:
    """Tell the winner about a seller decision (approve / reject / handover / pickup failed)."""
    winner = winner_id(db, listing)
    if winner is not None:
        notify(db, winner, type, title, body, listing.id, actor_id=actor_id)


# --- reading ----------------------------------------------------------------


def unread_count(db: Session, user_id: int) -> int:
    return db.scalar(
        select(func.count()).select_from(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
    )


def list_for_user(
    db: Session, user_id: int, since_id: int | None, unread_only: bool, limit: int, before_id: int | None = None
) -> list[Notification]:
    """With `since_id`: a cursor feed, oldest first, so a poller can safely advance its cursor.
    Without it: a history view, newest first; `before_id` continues it with older items."""
    query = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    if since_id is not None:
        query = query.where(Notification.id > since_id).order_by(Notification.id.asc())
    else:
        if before_id is not None:
            query = query.where(Notification.id < before_id)
        query = query.order_by(Notification.id.desc())
    return list(db.scalars(query.limit(limit)).all())


def mark_read(db: Session, user_id: int, notification_id: int, now: datetime | None = None) -> bool:
    """Mark one of the user's notifications read. False if it isn't theirs (or doesn't exist)."""
    note = db.get(Notification, notification_id)
    if note is None or note.user_id != user_id:
        return False
    if note.read_at is None:
        note.read_at = now or utcnow()
        db.commit()
    return True  # already read: nothing to change, still a success


def mark_all_read(db: Session, user_id: int, now: datetime | None = None) -> int:
    result = db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        .values(read_at=now or utcnow())
    )
    db.commit()
    return result.rowcount
