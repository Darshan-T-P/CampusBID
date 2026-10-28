from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.models import Listing
from app.schemas.bid import BidCreate, BidPublic, BidResult
from app.services import bids as bid_service
from app.services import listings as listing_service
from app.services.auction import BidError, place_bid

router = APIRouter(tags=["bids"])

_HTTP_STATUS = {
    "not_found": status.HTTP_404_NOT_FOUND,
    "own_listing": status.HTTP_403_FORBIDDEN,
    "closed": status.HTTP_409_CONFLICT,
    "too_low": status.HTTP_409_CONFLICT,  # state moved on: someone may have bid higher meanwhile
}


@router.post("/listings/{listing_id}/bids", response_model=BidResult, status_code=status.HTTP_201_CREATED)
def create_bid(listing_id: int, body: BidCreate, user: CurrentUser, db: DbSession):
    try:
        bid = place_bid(db, listing_id, user.id, body.amount)
    except BidError as e:
        # A structured detail so the UI can react to the code (e.g. refresh the minimum bid).
        detail = {"code": e.code, "message": e.message}
        if e.min_bid is not None:
            detail["min_bid"] = e.min_bid
        raise HTTPException(_HTTP_STATUS[e.code], detail) from e
    listing = db.get(Listing, listing_id)
    return BidResult(
        bid=bid_service.to_public(bid),
        listing=listing_service.listing_detail(db, listing),
    )


@router.get("/listings/{listing_id}/bids", response_model=list[BidPublic])
def list_bids(listing_id: int, db: DbSession):
    if db.get(Listing, listing_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Listing not found")
    return bid_service.bid_history(db, listing_id)
