from pydantic import BaseModel


class PriceSuggestion(BaseModel):
    """What similar items really sold for here. Aggregates only: no sellers, no buyers, no listings."""

    count: int  # how many sales it is based on (0 = not enough to say anything)
    basis: str | None = None  # "similar" (same words), "condition" (same category and condition) or "category"
    low: int | None = None  # a typical low final price (the 25th percentile)
    median: int | None = None
    high: int | None = None  # a typical high final price (the 75th percentile)
    suggested_start: int | None = None  # a starting price that invites early bids
