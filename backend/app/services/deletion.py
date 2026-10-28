"""Deleting an account.

Someone can leave only when no other student is waiting on them: no open auction of theirs, no sale in
progress, no lead on an open auction. After that, everything that was only theirs goes (notifications, saved
auctions, automatic bids, codes). If they never listed or bid, the account row goes too and the email is free
again. Otherwise the row stays as "Deleted user", because other students' bid histories and sales point at it;
the email, name, department, year and password are wiped, so nothing identifies them any more.
"""

from datetime import datetime

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.models import (
    AutoBid,
    Bid,
    ClosingReminder,
    EmailVerification,
    Listing,
    ListingStatus,
    Notification,
    PasswordReset,
    User,
    Watch,
)
from app.services.auction import begin_write, close_if_due
from app.services.errors import AccountError

IN_PROGRESS = (ListingStatus.pending_approval, ListingStatus.reserved)


def blockers(db: Session, user_id: int) -> list[str]:
    """Plain-language reasons this person can't leave yet (empty = free to go)."""
    reasons = []
    selling_open = db.scalar(
        select(func.count()).select_from(Listing).where(Listing.seller_id == user_id, Listing.status == ListingStatus.active)
    )
    if selling_open:
        reasons.append(f"you have {selling_open} open auction{'s' if selling_open != 1 else ''} (cancel or let them end first)")
    selling_sales = db.scalar(
        select(func.count()).select_from(Listing).where(Listing.seller_id == user_id, Listing.status.in_(IN_PROGRESS))
    )
    if selling_sales:
        reasons.append(f"{selling_sales} of your sales {'are' if selling_sales != 1 else 'is'} still waiting for a decision or a handover")
    leading = db.scalar(
        select(func.count()).select_from(Listing).join(Bid, Bid.id == Listing.leading_bid_id)
        .where(Bid.bidder_id == user_id, Listing.status == ListingStatus.active)
    )
    if leading:
        reasons.append(f"you are leading {leading} open auction{'s' if leading != 1 else ''}")
    buying_sales = db.scalar(
        select(func.count()).select_from(Listing).join(Bid, Bid.id == Listing.leading_bid_id)
        .where(Bid.bidder_id == user_id, Listing.status.in_(IN_PROGRESS))
    )
    if buying_sales:
        reasons.append(f"you won {buying_sales} item{'s' if buying_sales != 1 else ''} that {'are' if buying_sales != 1 else 'is'} still being settled")
    return reasons


def delete_account(db: Session, user_id: int, now: datetime | None = None) -> str:
    """Delete or anonymise the account. Returns "deleted" or "anonymised". Raises AccountError if blocked."""
    now = now or utcnow()
    begin_write(db)  # no bid or sale can slip in between the checks and the change
    try:
        user = db.scalars(select(User).where(User.id == user_id).execution_options(populate_existing=True)).one()
        # An auction that already ran out of time shouldn't block anyone: settle it first.
        for listing in db.scalars(
            select(Listing).where(or_(Listing.seller_id == user_id, Listing.leading_bid_id.is_not(None)), Listing.status == ListingStatus.active)
        ).all():
            close_if_due(db, listing, now)
        db.flush()
        reasons = blockers(db, user_id)
        if reasons:
            db.commit()  # keep the settled auctions
            raise AccountError("You can't delete your account yet: " + "; ".join(reasons) + ".", "conflict")

        for model in (Notification, Watch, ClosingReminder, AutoBid, EmailVerification, PasswordReset):
            db.execute(delete(model).where(model.user_id == user_id))
        has_history = (
            db.scalar(select(func.count()).select_from(Listing).where(Listing.seller_id == user_id))
            or db.scalar(select(func.count()).select_from(Bid).where(Bid.bidder_id == user_id))
        )
        if has_history:
            user.email = f"deleted-{user.id}@deleted.invalid"
            user.display_name = "Deleted user"
            user.department = None
            user.year_of_study = None
            user.password_hash = "!deleted"  # matches no password
            user.is_verified = False
            user.password_changed_at = now
            user.deleted_at = now  # tokens are refused from here on, even ones issued a moment ago
            outcome = "anonymised"
        else:
            db.delete(user)
            outcome = "deleted"
        db.commit()
        return outcome
    except BaseException:
        db.rollback()
        raise
