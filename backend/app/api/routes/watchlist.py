from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession
from app.api.errors import listing_http_error
from app.core.ratelimit import enforce
from app.schemas.listing import ListingCard
from app.services import watchlist as service
from app.services.errors import ListingError

router = APIRouter(tags=["watchlist"])


@router.get("/me/watchlist", response_model=list[ListingCard])
def my_watchlist(user: CurrentUser, db: DbSession):
    """Auctions I saved: open ones first (closing soonest at the top), then ended ones."""
    return service.my_watchlist(db, user.id)


@router.put("/listings/{listing_id}/watch", status_code=status.HTTP_204_NO_CONTENT)
def watch(listing_id: int, user: CurrentUser, db: DbSession):
    """Save an auction to get closing reminders and the result. Saving again is harmless."""
    enforce(f"watch:user:{user.id}", limit=120, window=3600)
    try:
        service.watch(db, listing_id, user.id)
    except ListingError as e:
        raise listing_http_error(e) from e


@router.delete("/listings/{listing_id}/watch", status_code=status.HTTP_204_NO_CONTENT)
def unwatch(listing_id: int, user: CurrentUser, db: DbSession):
    enforce(f"watch:user:{user.id}", limit=120, window=3600)
    service.unwatch(db, listing_id, user.id)
