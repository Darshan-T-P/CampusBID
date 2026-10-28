from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.api.deps import CurrentUser, DbSession
from app.models import Category, Condition, Listing
from app.schemas.listing import ListingDetail
from app.services import listings as listing_service
from app.services.auction import ensure_closed
from app.services.listings import MAX_IMAGE_BYTES, ListingError

router = APIRouter(tags=["listings"])


@router.post("/listings", response_model=ListingDetail, status_code=status.HTTP_201_CREATED)
def create_listing(
    user: CurrentUser,
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
    # Read at most one byte past the limit: enough to detect "too big" without loading a huge upload.
    blobs = [f.file.read(MAX_IMAGE_BYTES + 1) for f in images]
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
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    return listing_service.listing_detail(db, listing)


@router.get("/listings/{listing_id}", response_model=ListingDetail)
def get_listing(listing_id: int, db: DbSession):
    listing = db.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Listing not found")
    ensure_closed(db, listing)  # reads never show a stale "active" for an expired auction
    return listing_service.listing_detail(db, listing)
