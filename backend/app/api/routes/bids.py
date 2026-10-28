from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbSession, VerifiedUser
from app.core.ratelimit import enforce
from app.core.events import broadcaster
from app.models import Listing
from app.schemas.bid import AutoBidCreate, AutoBidPublic, AutoBidResult, BidCreate, BidPublic, BidResult
from app.services import bids as bid_service
from app.services import listings as listing_service
from app.services.auction import KEEP_STEP, BidError, place_bid, remove_auto_bid, set_auto_bid

router = APIRouter(tags=["bids"])

_HTTP_STATUS = {
    "not_found": status.HTTP_404_NOT_FOUND,
    "own_listing": status.HTTP_403_FORBIDDEN,
    "closed": status.HTTP_409_CONFLICT,
    "already_leading": status.HTTP_409_CONFLICT,  # raising your own lead only pushes the price up
    "too_low": status.HTTP_409_CONFLICT,  # state moved on: someone may have bid higher meanwhile
    "invalid_step": status.HTTP_422_UNPROCESSABLE_CONTENT,  # a raise per bid below the auction's minimum
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
    public_bid = bid_service.to_public(bid)
    public_detail = listing_service.listing_detail(db, listing)

    # Real-time event push to all active viewers
    broadcaster.publish_nowait(
        "bid",
        {
            "listing_id": listing_id,
            "bid": public_bid.model_dump(mode="json"),
            "listing": public_detail.model_dump(mode="json"),
        },
        listing_id=listing_id,
    )

    return BidResult(
        bid=public_bid,
        listing=public_detail,
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
        # Leaving "step" out of the request keeps the raise they already chose; sending null resets it to the auction's minimum.
        step = body.step if "step" in body.model_fields_set else KEEP_STEP
        auto = set_auto_bid(db, listing_id, user.id, body.max_amount, step=step)
    except BidError as e:
        raise _bid_http_error(e) from e
    listing = db.get(Listing, listing_id)
    db.refresh(listing)  # the resolver may have moved the price
    public_auto = bid_service.auto_bid_to_public(auto)
    public_detail = listing_service.listing_detail(db, listing)

    # Real-time event push for auto-bid / proxy updates
    broadcaster.publish_nowait(
        "bid",
        {
            "listing_id": listing_id,
            "auto_bid": public_auto.model_dump(mode="json"),
            "listing": public_detail.model_dump(mode="json"),
        },
        listing_id=listing_id,
    )

    return AutoBidResult(
        auto_bid=public_auto,
        listing=public_detail,
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
