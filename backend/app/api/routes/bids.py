from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbSession, VerifiedUser
from app.core.ratelimit import enforce
from app.models import Listing
from app.schemas.bid import AutoBidCreate, AutoBidPublic, AutoBidResult, BidCreate, BidPublic, BidResult
from app.services import bids as bid_service
from app.services import listings as listing_service
from app.services.auction import BidError, place_bid, remove_auto_bid, set_auto_bid

router = APIRouter(tags=["bids"])

_HTTP_STATUS = {
    "not_found": status.HTTP_404_NOT_FOUND,
    "own_listing": status.HTTP_403_FORBIDDEN,
    "closed": status.HTTP_409_CONFLICT,
    "already_leading": status.HTTP_409_CONFLICT,  # raising your own lead only pushes the price up
    "too_low": status.HTTP_409_CONFLICT,  # state moved on: someone may have bid higher meanwhile
}


@router.post("/listings/{listing_id}/bids", response_model=BidResult, status_code=status.HTTP_201_CREATED)
def create_bid(listing_id: int, body: BidCreate, user: VerifiedUser, db: DbSession):
    enforce(f"bid:user:{user.id}", limit=60, window=60)  # plenty for a human, a wall for a script
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


def _bid_http_error(e: BidError) -> HTTPException:
    detail = {"code": e.code, "message": e.message}
    if e.min_bid is not None:
        detail["min_bid"] = e.min_bid
    return HTTPException(_HTTP_STATUS[e.code], detail)


@router.put("/listings/{listing_id}/auto-bid", response_model=AutoBidResult)
def put_auto_bid(listing_id: int, body: AutoBidCreate, user: VerifiedUser, db: DbSession):
    """Set or change my maximum: the app bids for me, as little as needed, up to it."""
    enforce(f"autobid:user:{user.id}", limit=30, window=60)
    try:
        auto = set_auto_bid(db, listing_id, user.id, body.max_amount)
    except BidError as e:
        raise _bid_http_error(e) from e
    listing = db.get(Listing, listing_id)
    db.refresh(listing)  # the resolver may have moved the price
    return AutoBidResult(
        auto_bid=bid_service.auto_bid_to_public(auto),
        listing=listing_service.listing_detail(db, listing),
    )


@router.delete("/listings/{listing_id}/auto-bid", status_code=status.HTTP_204_NO_CONTENT)
def delete_auto_bid(listing_id: int, user: VerifiedUser, db: DbSession):
    try:
        remove_auto_bid(db, listing_id, user.id)
    except BidError as e:
        raise _bid_http_error(e) from e


@router.get("/listings/{listing_id}/auto-bids", response_model=list[AutoBidPublic])
def list_auto_bids(listing_id: int, db: DbSession):
    """Everyone's standing maximums on this auction. Public: nothing about bidding is private."""
    if db.get(Listing, listing_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Listing not found")
    return bid_service.list_auto_bids(db, listing_id)
