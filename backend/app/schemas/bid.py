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


class AutoBidCreate(BaseModel):
    max_amount: int = Field(ge=1, le=MAX_PRICE, description="The most you are willing to pay, whole rupees")


class AutoBidPublic(BaseModel):
    """A standing maximum. Public by design: nothing about bidding is private."""

    bidder_name: str
    max_amount: int
    set_at: datetime


class AutoBidResult(BaseModel):
    auto_bid: AutoBidPublic
    listing: ListingDetail


class MyAutoBid(BaseModel):
    listing_id: int
    max_amount: int
