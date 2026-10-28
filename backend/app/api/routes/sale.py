from typing import Annotated

from fastapi import APIRouter, Body

from app.api.deps import CurrentUser, DbSession
from app.api.errors import listing_http_error
from app.schemas.listing import ListingDetail
from app.core.ratelimit import enforce
from app.schemas.sale import ContactInfo, RejectRequest
from app.services import listings as listing_service
from app.services import sale as sale_service
from app.services.errors import ListingError

router = APIRouter(tags=["sale"])


def _detail(db, listing):
    return listing_service.listing_detail(db, listing)


@router.post("/listings/{listing_id}/approve", response_model=ListingDetail)
def approve(listing_id: int, user: CurrentUser, db: DbSession):
    """Seller accepts the winning bid: pending_approval -> reserved."""
    try:
        return _detail(db, sale_service.approve(db, listing_id, user.id))
    except ListingError as e:
        raise listing_http_error(e) from e


@router.post("/listings/{listing_id}/reject", response_model=ListingDetail)
def reject(
    listing_id: int,
    user: CurrentUser,
    db: DbSession,
    body: Annotated[RejectRequest | None, Body()] = None,
):
    """Seller turns the winning bid down: pending_approval -> rejected. A reason is optional."""
    try:
        reason = body.reason if body else None
        return _detail(db, sale_service.reject(db, listing_id, user.id, reason))
    except ListingError as e:
        raise listing_http_error(e) from e


@router.post("/listings/{listing_id}/handover", response_model=ListingDetail)
def handover(listing_id: int, user: CurrentUser, db: DbSession):
    """Item changed hands: reserved -> completed."""
    try:
        return _detail(db, sale_service.confirm_handover(db, listing_id, user.id))
    except ListingError as e:
        raise listing_http_error(e) from e


@router.post("/listings/{listing_id}/pickup-failed", response_model=ListingDetail)
def pickup_failed(listing_id: int, user: CurrentUser, db: DbSession):
    """Winner never collected it: reserved -> failed_pickup."""
    try:
        return _detail(db, sale_service.pickup_failed(db, listing_id, user.id))
    except ListingError as e:
        raise listing_http_error(e) from e


@router.get("/listings/{listing_id}/contact", response_model=ContactInfo)
def contact(listing_id: int, user: CurrentUser, db: DbSession):
    """The other side's name and mobile number. Only the seller and the winner, only after approval."""
    enforce(f"contact:user:{user.id}", limit=60, window=600)
    try:
        return sale_service.contact_details(db, listing_id, user.id)
    except ListingError as e:
        raise listing_http_error(e) from e
