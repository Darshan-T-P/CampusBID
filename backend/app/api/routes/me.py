from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.listing import ListingPage, MyBid
from app.services import listings as listing_service

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/listings", response_model=ListingPage)
def my_listings(
    user: CurrentUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Everything I'm selling, in any status, newest first."""
    return listing_service.search_listings(
        db,
        status=None,
        seller_id=user.id,
        sort=listing_service.Sort.newest,
        limit=limit,
        offset=offset,
    )


@router.get("/bids", response_model=list[MyBid])
def my_bids(user: CurrentUser, db: DbSession):
    """Every listing I've bid on, with my best bid and whether I'm currently leading."""
    return listing_service.my_bids(db, user.id)
