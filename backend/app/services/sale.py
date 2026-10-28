"""The sale workflow: what happens after an auction closes with a winning bid.

    pending_approval --approve--> reserved --handover--> completed
          |                           `--pickup_failed--> failed_pickup
          `--reject--> rejected

Every step is a compare-and-swap on the expected current status, taken under the write lock,
so double-clicks, two open tabs and racing approve/reject calls can never apply twice.
"""

from collections.abc import Callable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.models import Listing, ListingStatus, User
from app.schemas.sale import ContactInfo
from app.services import notifications
from app.services.auction import begin_write, close_if_due
from app.services.errors import ListingError

_ALREADY = {
    ListingStatus.pending_approval: "is still waiting for the seller's decision",
    ListingStatus.reserved: "is already approved",
    ListingStatus.completed: "is already completed",
    ListingStatus.failed_pickup: "already ended with a failed pickup",
    ListingStatus.rejected: "was already rejected",
    ListingStatus.unsold: "closed with no bids",
    ListingStatus.cancelled: "was cancelled",
    ListingStatus.active: "is still open for bidding",
}


def _transition(
    db: Session,
    listing_id: int,
    user_id: int,
    expected: ListingStatus,
    new: ListingStatus,
    note: Callable[[Listing], str],
    event: tuple[str, str, Callable[[Listing], str]],
    now: datetime | None = None,
) -> Listing:
    """`note` builds the public outcome text; `event` is (notification type, title, body builder)
    for the message the winner receives."""
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
        close_if_due(db, listing, now)  # an expired-but-unswept auction becomes pending_approval first
        if listing.status != expected:
            raise ListingError(f"This listing {_ALREADY[listing.status]}", "conflict")
        listing.status = new
        listing.outcome_note = note(listing)
        kind, title, body = event
        notifications.sale_step(db, listing, user_id, kind, f"{title}: {listing.title}", body(listing))
        db.commit()
        return listing
    except BaseException:
        db.rollback()
        raise


def approve(db: Session, listing_id: int, user_id: int, now: datetime | None = None) -> Listing:
    return _transition(
        db, listing_id, user_id, ListingStatus.pending_approval, ListingStatus.reserved,
        lambda l: f"Approved by the seller at {l.current_price}; awaiting handover" + (f" at {l.handover_spot}" if l.handover_spot else ""),
        ("approved", "Sale approved", lambda l: f"The seller approved your bid of ₹{l.current_price}. "
            + (f"Meet at {l.handover_spot} to hand over the item." if l.handover_spot else "Arrange the handover with the seller.")
            + " Open the listing to see the seller's contact number."), now,
    )


def reject(
    db: Session, listing_id: int, user_id: int, reason: str | None = None, now: datetime | None = None
) -> Listing:
    note = "Rejected by the seller"
    if reason and reason.strip():
        note += f": {reason.strip()}"
    return _transition(
        db, listing_id, user_id, ListingStatus.pending_approval, ListingStatus.rejected,
        lambda _l: note,
        ("rejected", "Sale rejected", lambda _l: note + "."), now,
    )


def confirm_handover(db: Session, listing_id: int, user_id: int, now: datetime | None = None) -> Listing:
    return _transition(
        db, listing_id, user_id, ListingStatus.reserved, ListingStatus.completed,
        lambda l: f"Handed over; sale completed at {l.current_price}",
        ("completed", "Sale completed", lambda l: f"Handover confirmed at ₹{l.current_price}. Enjoy!"), now,
    )


def pickup_failed(db: Session, listing_id: int, user_id: int, now: datetime | None = None) -> Listing:
    return _transition(
        db, listing_id, user_id, ListingStatus.reserved, ListingStatus.failed_pickup,
        lambda _l: "The winner did not collect the item",
        ("pickup_failed", "Pickup not completed", lambda _l: "The seller recorded that the item was not collected."), now,
    )


def contact_details(db: Session, listing_id: int, user_id: int) -> ContactInfo:
    """The other side's name and number, for the seller and the winner only, and only once the sale is approved.

    Everywhere else a phone number never leaves the account that owns it.
    """
    listing = db.get(Listing, listing_id)
    if listing is None:
        raise ListingError("Listing not found", "not_found")
    winner = notifications.winner_id(db, listing)
    if user_id not in (listing.seller_id, winner):
        raise ListingError("Contact details are shared only between the seller and the winner", "forbidden")
    if listing.status != ListingStatus.reserved:
        raise ListingError("Contact details are shared once the seller approves the sale", "conflict")
    seller_side = user_id == listing.seller_id
    other = db.get(User, winner if seller_side else listing.seller_id)
    return ContactInfo(
        role="buyer" if seller_side else "seller",
        name=other.display_name,
        phone=other.phone,
        listing_title=listing.title,
    )
