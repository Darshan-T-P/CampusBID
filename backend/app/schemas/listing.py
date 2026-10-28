from datetime import datetime

from pydantic import BaseModel

from app.models import Category, Condition, ListingStatus


class SellerPublic(BaseModel):
    id: int
    display_name: str


class ListingDetail(BaseModel):
    """Everything the public may see about a listing. No emails, no password data."""

    id: int
    title: str
    category: Category
    condition: Condition
    description: str
    starting_price: int
    min_increment: int
    closes_at: datetime
    status: ListingStatus
    current_price: int | None
    # Lowest amount a new bid may be right now; None once bidding is closed.
    min_next_bid: int | None
    bid_count: int
    leading_bidder: str | None  # display name only
    outcome_note: str | None
    images: list[str]  # URLs under /media
    seller: SellerPublic
    created_at: datetime
    # Clients render countdowns from closes_at against this, never their own clock.
    server_time: datetime
