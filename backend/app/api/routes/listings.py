from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status

from app.api.deps import CurrentUser, DbSession, VerifiedUser
from app.models import Category, Condition, Listing, ListingStatus
from app.schemas.listing import ListingDetail, ListingPage, ListingUpdate
from app.services import listings as listing_service
from app.services.auction import cancel_listing, ensure_closed
from app.services.errors import ListingError
from app.services.listings import MAX_IMAGE_BYTES, Sort

router = APIRouter(tags=["listings"])

_HTTP_STATUS = {
    "invalid": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "not_found": status.HTTP_404_NOT_FOUND,
    "forbidden": status.HTTP_403_FORBIDDEN,
    "conflict": status.HTTP_409_CONFLICT,
}


def _http_error(e: ListingError) -> HTTPException:
    return HTTPException(_HTTP_STATUS[e.code], e.message)


def _read_uploads(files: list[UploadFile]) -> list[bytes]:
    # Read at most one byte past the limit: enough to detect "too big" without loading a huge upload.
    return [f.file.read(MAX_IMAGE_BYTES + 1) for f in files]


@router.post("/listings", response_model=ListingDetail, status_code=status.HTTP_201_CREATED)
def create_listing(
    user: VerifiedUser,
    db: DbSession,
    title: Annotated[str, Form(max_length=120)],
    category: Annotated[Category, Form()],
    condition: Annotated[Condition, Form()],
    starting_price: Annotated[int, Form(ge=1)],
    closes_at: Annotated[datetime, Form()],
    min_increment: Annotated[int, Form(ge=1)] = 1,
    description: Annotated[str, Form(max_length=5000)] = "",
    images: Annotated[list[UploadFile], File()] = [],
):
    blobs = _read_uploads(images)
    try:
        listing = listing_service.create_listing(
            db,
            user,
            title=title,
            category=category,
            condition=condition,
            description=description,
            starting_price=starting_price,
            min_increment=min_increment,
            closes_at=closes_at,
            images=blobs,
        )
    except ListingError as e:
        raise _http_error(e) from e
    return listing_service.listing_detail(db, listing)


@router.get("/listings", response_model=ListingPage)
def browse_listings(
    db: DbSession,
    q: Annotated[str | None, Query(max_length=100, description="Words to find in title/description")] = None,
    category: Category | None = None,
    condition: Condition | None = None,
    min_price: Annotated[int | None, Query(ge=0)] = None,
    max_price: Annotated[int | None, Query(ge=0)] = None,
    closing_soon: Annotated[bool, Query(description="Only auctions closing within the hour")] = False,
    # Python name differs from the public "status" param so it doesn't shadow fastapi.status.
    listing_status: Annotated[ListingStatus, Query(alias="status")] = ListingStatus.active,
    sort: Sort = Sort.ending_soon,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "min_price cannot exceed max_price")
    return listing_service.search_listings(
        db,
        q=q,
        category=category,
        condition=condition,
        min_price=min_price,
        max_price=max_price,
        closing_soon=closing_soon,
        status=listing_status,
        sort=sort,
        limit=limit,
        offset=offset,
    )


@router.get("/listings/{listing_id}", response_model=ListingDetail)
def get_listing(listing_id: int, db: DbSession):
    listing = db.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Listing not found")
    ensure_closed(db, listing)  # reads never show a stale "active" for an expired auction
    return listing_service.listing_detail(db, listing)


@router.patch("/listings/{listing_id}", response_model=ListingDetail)
def edit_listing(listing_id: int, body: ListingUpdate, user: CurrentUser, db: DbSession):
    changes = body.model_dump(exclude_unset=True)  # only what the client actually sent
    if not changes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "No changes given")
    try:
        listing = listing_service.update_listing(db, listing_id, user.id, changes)
    except ListingError as e:
        raise _http_error(e) from e
    return listing_service.listing_detail(db, listing)


@router.post("/listings/{listing_id}/cancel", response_model=ListingDetail)
def cancel(listing_id: int, user: CurrentUser, db: DbSession):
    try:
        listing = cancel_listing(db, listing_id, user.id)
    except ListingError as e:
        raise _http_error(e) from e
    return listing_service.listing_detail(db, listing)


@router.post("/listings/{listing_id}/images", response_model=ListingDetail)
def add_photos(
    listing_id: int,
    user: CurrentUser,
    db: DbSession,
    images: Annotated[list[UploadFile], File()] = [],
):
    try:
        listing = listing_service.add_images(db, listing_id, user.id, _read_uploads(images))
    except ListingError as e:
        raise _http_error(e) from e
    return listing_service.listing_detail(db, listing)


@router.delete("/listings/{listing_id}/images/{image_id}", response_model=ListingDetail)
def remove_photo(listing_id: int, image_id: int, user: CurrentUser, db: DbSession):
    try:
        listing = listing_service.remove_image(db, listing_id, user.id, image_id)
    except ListingError as e:
        raise _http_error(e) from e
    return listing_service.listing_detail(db, listing)
