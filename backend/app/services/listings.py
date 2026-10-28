"""Creating and presenting listings. Bidding and closing rules live in auction.py."""

import enum
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.clock import utcnow
from app.core.config import settings
from app.models import Bid, Category, Condition, Listing, ListingImage, ListingStatus, User
from app.schemas.listing import ListingCard, ListingDetail, ListingPage, SellerPublic
from app.services.auction import min_valid_bid

MIN_IMAGES = 1
MAX_IMAGES = 5
MAX_IMAGE_BYTES = 5 * 1024 * 1024
CLOSING_SOON = timedelta(hours=1)  # the "closing soon" filter window


class ListingError(Exception):
    """A listing was refused because the input breaks a rule (maps to HTTP 422)."""


def sniff_image_ext(data: bytes) -> str | None:
    """Identify the image type from its first bytes, ignoring any client-supplied name or type."""
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _validate_images(images: list[bytes]) -> list[str]:
    if not MIN_IMAGES <= len(images) <= MAX_IMAGES:
        raise ListingError(f"Attach {MIN_IMAGES} to {MAX_IMAGES} photos")
    extensions = []
    for data in images:
        if len(data) > MAX_IMAGE_BYTES:
            raise ListingError(f"Each photo must be under {MAX_IMAGE_BYTES // (1024 * 1024)} MB")
        ext = sniff_image_ext(data)
        if ext is None:
            raise ListingError("Photos must be JPEG, PNG or WebP images")
        extensions.append(ext)
    return extensions


def create_listing(
    db: Session,
    seller: User,
    *,
    title: str,
    category: Category,
    condition: Condition,
    description: str,
    starting_price: int,
    min_increment: int,
    closes_at: datetime,
    images: list[bytes],
    now: datetime | None = None,
) -> Listing:
    now = now or utcnow()
    title = title.strip()
    if not title:
        raise ListingError("Title is required")
    if starting_price < 1 or min_increment < 1:
        raise ListingError("Starting price and minimum increment must be at least 1")
    if closes_at.tzinfo is None:
        raise ListingError("closes_at must include a timezone, e.g. 2026-05-01T18:00:00Z")
    if closes_at <= now:
        raise ListingError("closes_at must be in the future")
    extensions = _validate_images(images)

    listing = Listing(
        seller_id=seller.id,
        title=title,
        category=category,
        condition=condition,
        description=description.strip(),
        starting_price=starting_price,
        min_increment=min_increment,
        closes_at=closes_at,
    )
    db.add(listing)
    db.flush()  # assigns listing.id, needed for the photo folder name

    folder = Path(settings.media_dir) / "listings" / str(listing.id)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        for position, (data, ext) in enumerate(zip(images, extensions)):
            name = f"{uuid.uuid4().hex}.{ext}"  # server-chosen name: nothing user-controlled
            (folder / name).write_bytes(data)
            listing.images.append(ListingImage(path=f"listings/{listing.id}/{name}", position=position))
        db.commit()
    except BaseException:
        db.rollback()
        shutil.rmtree(folder, ignore_errors=True)  # don't leave orphan files behind
        raise
    return listing


def listing_detail(db: Session, listing: Listing, now: datetime | None = None) -> ListingDetail:
    leading_bidder = None
    if listing.leading_bid_id is not None:
        bid = db.get(Bid, listing.leading_bid_id)
        leading_bidder = bid.bidder.display_name
    bid_count = db.scalar(select(func.count()).select_from(Bid).where(Bid.listing_id == listing.id))
    return ListingDetail(
        id=listing.id,
        title=listing.title,
        category=listing.category,
        condition=listing.condition,
        description=listing.description,
        starting_price=listing.starting_price,
        min_increment=listing.min_increment,
        closes_at=listing.closes_at,
        status=listing.status,
        current_price=listing.current_price,
        min_next_bid=min_valid_bid(listing) if listing.status == ListingStatus.active else None,
        bid_count=bid_count,
        leading_bidder=leading_bidder,
        outcome_note=listing.outcome_note,
        images=[f"/media/{img.path}" for img in listing.images],
        seller=SellerPublic(id=listing.seller.id, display_name=listing.seller.display_name),
        created_at=listing.created_at,
        server_time=now or utcnow(),
    )


class Sort(str, enum.Enum):
    ending_soon = "ending_soon"
    newest = "newest"
    price_low = "price_low"
    price_high = "price_high"


def _escape_like(term: str) -> str:
    """Make %, _ and \\ literal so a search for "50%" isn't a wildcard."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_listings(
    db: Session,
    *,
    q: str | None = None,
    category: Category | None = None,
    condition: Condition | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    closing_soon: bool = False,
    status: ListingStatus = ListingStatus.active,
    sort: Sort = Sort.ending_soon,
    limit: int = 20,
    offset: int = 0,
    now: datetime | None = None,
) -> ListingPage:
    now = now or utcnow()
    # The price a buyer actually faces: the leading bid, or the starting price if no bids yet.
    price = func.coalesce(Listing.current_price, Listing.starting_price)

    conditions = [Listing.status == status]
    if status == ListingStatus.active:
        # Filter on time too, so an expired auction the background closer hasn't reached
        # yet never shows up as open.
        conditions.append(Listing.closes_at > now)
    if category is not None:
        conditions.append(Listing.category == category)
    if condition is not None:
        conditions.append(Listing.condition == condition)
    if min_price is not None:
        conditions.append(price >= min_price)
    if max_price is not None:
        conditions.append(price <= max_price)
    if closing_soon:
        conditions.append(Listing.closes_at <= now + CLOSING_SOON)
    for term in (q or "").split():  # every word must match the title or the description
        pattern = f"%{_escape_like(term)}%"
        conditions.append(
            or_(
                Listing.title.ilike(pattern, escape="\\"),
                Listing.description.ilike(pattern, escape="\\"),
            )
        )

    order_by = {
        Sort.ending_soon: [Listing.closes_at.asc()],
        Sort.newest: [Listing.created_at.desc()],
        Sort.price_low: [price.asc()],
        Sort.price_high: [price.desc()],
    }[sort] + [Listing.id.desc() if sort == Sort.newest else Listing.id.asc()]  # stable paging

    total = db.scalar(select(func.count()).select_from(Listing).where(*conditions))
    bid_count = (
        select(func.count()).where(Bid.listing_id == Listing.id).correlate(Listing).scalar_subquery()
    )
    rows = db.execute(
        select(Listing, bid_count)
        .where(*conditions)
        .order_by(*order_by)
        .limit(limit)
        .offset(offset)
        .options(selectinload(Listing.images), joinedload(Listing.seller))
    ).all()

    items = [
        ListingCard(
            id=listing.id,
            title=listing.title,
            category=listing.category,
            condition=listing.condition,
            status=listing.status,
            starting_price=listing.starting_price,
            current_price=listing.current_price,
            price=listing.current_price if listing.current_price is not None else listing.starting_price,
            bid_count=count,
            closes_at=listing.closes_at,
            thumbnail=f"/media/{listing.images[0].path}" if listing.images else None,
            seller_name=listing.seller.display_name,
        )
        for listing, count in rows
    ]
    return ListingPage(items=items, total=total, limit=limit, offset=offset, server_time=now)
