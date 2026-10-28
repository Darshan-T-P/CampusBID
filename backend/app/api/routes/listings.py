import asyncio
from datetime import datetime
import json
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, DbSession, VerifiedUser
from app.api.errors import listing_http_error
from app.core.events import broadcaster
from app.core.ratelimit import enforce
from app.models import Category, Condition, Listing, ListingStatus
from app.schemas.listing import ListingDetail, ListingPage, ListingUpdate
from app.services import listings as listing_service
from app.services.auction import cancel_listing, ensure_closed
from app.services.errors import ListingError
from app.services.listings import MAX_IMAGE_BYTES, MAX_PRICE, Sort

router = APIRouter(tags=["listings"])

STREAM_PING_SECONDS = 15.0  # a keep-alive comment this often, so proxies don't close an idle stream

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
    starting_price: Annotated[int, Form(ge=1, le=MAX_PRICE)],
    closes_at: Annotated[datetime, Form()],
    min_increment: Annotated[int, Form(ge=1, le=MAX_PRICE)] = 1,
    description: Annotated[str, Form(max_length=5000)] = "",
    handover_spot: Annotated[str | None, Form(max_length=120)] = None,
    confirm_duplicate: Annotated[bool, Form(description="Yes, this really is a second item")] = False,
    images: Annotated[list[UploadFile], File()] = [],
):
    enforce(f"list:user:{user.id}", limit=20, window=3600)
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
            handover_spot=handover_spot,
            confirm_duplicate=confirm_duplicate,
        )
    except listing_service.DuplicateListing as e:
        # Not an outright refusal: the app asks "is this a second item?" and the seller can say yes (confirm_duplicate).
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "code": "possible_duplicate",
                "message": e.message,
                "reason": e.reason,
                "existing": {
                    "id": e.existing.id,
                    "title": e.existing.title,
                    "status": e.existing.status.value,
                    "price": e.existing.current_price if e.existing.current_price is not None else e.existing.starting_price,
                },
            },
        ) from e
    except ListingError as e:
        raise listing_http_error(e) from e
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
        raise listing_http_error(e) from e
    return listing_service.listing_detail(db, listing)


@router.post("/listings/{listing_id}/cancel", response_model=ListingDetail)
def cancel(listing_id: int, user: CurrentUser, db: DbSession):
    try:
        listing = cancel_listing(db, listing_id, user.id)
    except ListingError as e:
        raise listing_http_error(e) from e
    detail = listing_service.listing_detail(db, listing)
    broadcaster.publish_nowait("status", {"listing_id": listing.id, "listing": detail.model_dump(mode="json")}, listing_id=listing.id)
    return detail


@router.post("/listings/{listing_id}/images", response_model=ListingDetail)
def add_photos(
    listing_id: int,
    user: CurrentUser,
    db: DbSession,
    images: Annotated[list[UploadFile], File()] = [],
):
    enforce(f"upload:user:{user.id}", limit=30, window=3600)
    try:
        listing = listing_service.add_images(db, listing_id, user.id, _read_uploads(images))
    except ListingError as e:
        raise listing_http_error(e) from e
    return listing_service.listing_detail(db, listing)


@router.delete("/listings/{listing_id}/images/{image_id}", response_model=ListingDetail)
def remove_photo(listing_id: int, image_id: int, user: CurrentUser, db: DbSession):
    try:
        listing = listing_service.remove_image(db, listing_id, user.id, image_id)
    except ListingError as e:
        raise listing_http_error(e) from e
    return listing_service.listing_detail(db, listing)


@router.get("/listings/{listing_id}/stream")
async def stream_listing_events(listing_id: int, request: Request, db: DbSession):
    """Server-Sent Events (SSE) push stream for real-time bid updates, extensions, and price changes."""
    exists = db.get(Listing, listing_id) is not None
    # A stream lives as long as the page is open. Holding this session (a pooled connection) for that long let about
    # fifteen open auction pages starve every other request, so give the connection back before streaming.
    db.close()
    if not exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Listing not found")

    async def event_generator():
        q = await broadcaster.subscribe(listing_id)
        try:
            # Initial connect handshake
            yield f"event: connect\ndata: {json.dumps({'listing_id': listing_id})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    # Wait for real-time event with 15s keep-alive timeout
                    msg = await asyncio.wait_for(q.get(), timeout=STREAM_PING_SECONDS)
                    event_type = msg.get("event", "message")
                    data_str = json.dumps(msg.get("data", {}))
                    yield f"event: {event_type}\ndata: {data_str}\n\n"
                except asyncio.TimeoutError:
                    # Keep-alive heartbeat comment to prevent proxy timeout
                    yield ": ping\n\n"
        finally:
            await broadcaster.unsubscribe(q, listing_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

