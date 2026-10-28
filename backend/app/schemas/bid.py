from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.listing import MAX_PRICE, ListingDetail


class BidCreate(BaseModel):
    amount: int = Field(ge=1, le=MAX_PRICE, description="Whole rupees")


class BidPublic(BaseModel):
    """A bid as anyone may see it: display name, amount, time. Never contact details."""

    id: int
    amount: int
    bidder_name: str
    created_at: datetime
    is_auto: bool


class BidResult(BaseModel):
    """What a successful bid returns: the bid, and the listing as it now stands."""

    bid: BidPublic
    listing: ListingDetail
