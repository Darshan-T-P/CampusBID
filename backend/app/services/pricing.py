"""Price suggestions for sellers, from what similar items actually sold for on this campus."""

import re
import statistics
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.models import Category, Condition, Listing, ListingStatus
from app.schemas.pricing import PriceSuggestion

# "Sold" means an auction that ended with a winner: approved, handed over, or waiting for the seller's decision.
SOLD = (ListingStatus.completed, ListingStatus.reserved, ListingStatus.pending_approval)
MIN_SALES = 3  # fewer than this and any number would be a guess
LOOKBACK = timedelta(days=180)
START_FRACTION = 0.7  # a start at about 70% of the typical final price invites early bids without giving it away
_FILLER = {"a", "an", "the", "of", "for", "and", "with", "set", "used", "new", "old", "good", "very"}


def _words(text: str | None) -> set[str]:
    return {w for w in re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split() if len(w) > 2 and w not in _FILLER}


def _percentile(sorted_prices: list[int], fraction: float) -> int:
    return sorted_prices[round(fraction * (len(sorted_prices) - 1))]


def _summary(prices: list[int], basis: str) -> PriceSuggestion:
    prices = sorted(prices)
    median = int(statistics.median(prices))
    start = max(50, round(median * START_FRACTION / 50) * 50)  # whole, tidy rupees
    return PriceSuggestion(
        count=len(prices), basis=basis, low=_percentile(prices, 0.25), median=median, high=_percentile(prices, 0.75),
        suggested_start=start,
    )


def suggest(db: Session, category: Category, condition: Condition | None, title: str | None, now: datetime | None = None) -> PriceSuggestion:
    """The closest group of past sales that has enough in it: same words, else same category and condition, else category."""
    now = now or utcnow()
    rows = db.execute(
        select(Listing.title, Listing.condition, Listing.current_price).where(
            Listing.category == category,
            Listing.status.in_(SOLD),
            Listing.current_price.is_not(None),
            Listing.closes_at >= now - LOOKBACK,
        )
    ).all()
    wanted = _words(title)
    if wanted:
        similar = [price for t, _c, price in rows if wanted & _words(t)]
        if len(similar) >= MIN_SALES:
            return _summary(similar, "similar")
    if condition is not None:
        same = [price for _t, c, price in rows if c == condition]
        if len(same) >= MIN_SALES:
            return _summary(same, "condition")
    if len(rows) >= MIN_SALES:
        return _summary([price for _t, _c, price in rows], "category")
    return PriceSuggestion(count=len(rows))
