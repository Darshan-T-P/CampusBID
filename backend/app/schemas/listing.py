from datetime import datetime

from pydantic import BaseModel

from app.models import Category, Condition, ListingStatus


class SellerPublic(BaseModel):
    id: int
    display_name: str


class ListingCard(BaseModel):
    """The slim version of a listing shown in browse results."""

    id: int
    title: str
    category: Category
    condition: Condition
    status: ListingStatus
    starting_price: int
    current_price: int | None
    price: int  # what a buyer faces now: the leading bid, or the starting price if no bids
    bid_count: int
    closes_at: datetime
    thumbnail: str | None  # first photo URL
    seller_name: str


class ListingPage(BaseModel):
    items: list[ListingCard]
    total: int  # matches across all pages, so the UI can page through
    limit: int
    offset: int
    server_time: datetime


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
