"""Saved wants ("never miss what you need").

A student saves what they are looking for: some words, a category, a price ceiling (any one, or all). When a new
listing is posted, every matching want produces a notification. Notifications are stored records, so a student who
was offline sees it later, and the bell's desktop pop-up covers the case where the app is open in another tab.
"""

import re

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.models import Category, Listing, Want
from app.services import notifications
from app.services.errors import ListingError

MAX_WANTS = 10  # per student: a cap so matching a new listing stays cheap and nobody is buried in alerts


def _clean_keywords(raw: str) -> str:
    return re.sub(r"\s+", " ", raw or "").strip()


def describe(want: Want) -> str:
    """'cycle, Cycles, under ₹2,000' for notifications."""
    parts = [want.keywords] if want.keywords else []
    if want.category is not None:
        parts.append(want.category.value)
    if want.max_price is not None:
        parts.append(f"under ₹{want.max_price:,}")
    return ", ".join(parts)


def create_want(db: Session, user_id: int, keywords: str, category: Category | None, max_price: int | None) -> Want:
    keywords = _clean_keywords(keywords)
    if not keywords and category is None and max_price is None:
        raise ListingError("Give at least a word, a category or a price limit", "invalid")
    existing = db.scalars(select(Want).where(Want.user_id == user_id)).all()
    if len(existing) >= MAX_WANTS:
        raise ListingError(f"You can keep up to {MAX_WANTS} alerts. Remove one first.", "conflict")
    if any(w.keywords.lower() == keywords.lower() and w.category == category and w.max_price == max_price for w in existing):
        raise ListingError("You already have that alert", "conflict")
    want = Want(user_id=user_id, keywords=keywords, category=category, max_price=max_price, created_at=utcnow())
    db.add(want)
    db.commit()
    return want


def list_wants(db: Session, user_id: int) -> list[Want]:
    return list(db.scalars(select(Want).where(Want.user_id == user_id).order_by(Want.id.desc())).all())


def delete_want(db: Session, user_id: int, want_id: int) -> None:
    want = db.get(Want, want_id)
    if want is None or want.user_id != user_id:  # someone else's alert looks exactly like a missing one
        raise ListingError("Alert not found", "not_found")
    db.delete(want)
    db.commit()


def _words_match(keywords: str, listing: Listing) -> bool:
    haystack = f"{listing.title} {listing.description or ''}".lower()
    return all(word in haystack for word in keywords.lower().split())


def notify_matches(db: Session, listing: Listing) -> int:
    """Called once when a listing is created, inside the same transaction. One notification per student, however many
    of their alerts match. Never the seller. Returns how many students were told."""
    candidates = db.scalars(
        select(Want).where(
            Want.user_id != listing.seller_id,
            or_(Want.category.is_(None), Want.category == listing.category),
            or_(Want.max_price.is_(None), Want.max_price >= listing.starting_price),
        )
    ).all()
    told: set[int] = set()
    for want in candidates:
        if want.user_id in told or not _words_match(want.keywords, listing):
            continue
        told.add(want.user_id)
        notifications.notify(
            db, want.user_id, "want_match", f"New listing for your alert: {listing.title}",
            f"Starts at ₹{listing.starting_price:,}. You asked for: {describe(want)}.",
            listing.id, now=listing.created_at,
        )
    return len(told)
