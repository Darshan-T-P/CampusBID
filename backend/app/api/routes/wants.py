from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession
from app.api.errors import listing_http_error
from app.core.ratelimit import enforce
from app.schemas.want import WantCreate, WantOut
from app.services import wants as service
from app.services.errors import ListingError

router = APIRouter(prefix="/me/wants", tags=["wants"])


@router.get("", response_model=list[WantOut])
def my_wants(user: CurrentUser, db: DbSession):
    """My saved alerts, newest first."""
    return service.list_wants(db, user.id)


@router.post("", response_model=WantOut, status_code=status.HTTP_201_CREATED)
def add_want(body: WantCreate, user: CurrentUser, db: DbSession):
    """Save an alert: I'll be notified when a new listing matches these words, category and price limit."""
    enforce(f"wants:user:{user.id}", limit=30, window=3600)
    try:
        return service.create_want(db, user.id, body.keywords, body.category, body.max_price)
    except ListingError as e:
        raise listing_http_error(e) from e


@router.delete("/{want_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_want(want_id: int, user: CurrentUser, db: DbSession):
    try:
        service.delete_want(db, user.id, want_id)
    except ListingError as e:
        raise listing_http_error(e) from e
