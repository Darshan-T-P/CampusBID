"""Creating and presenting listings. Bidding and closing rules live in auction.py."""

import enum
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.clock import utcnow
from app.core.config import settings
from app.models import Bid, Category, Condition, Listing, ListingImage, ListingStatus, User
from app.schemas.listing import ListingCard, ListingDetail, ListingPage, MyBid, SellerPublic
from app.services.auction import lock_listing_for_seller, min_valid_bid
from app.services.errors import ListingError

MIN_IMAGES = 1
MAX_IMAGES = 5
MAX_IMAGE_BYTES = 5 * 1024 * 1024
CLOSING_SOON = timedelta(hours=24)  # the "closing soon" filter window
MIN_DURATION = timedelta(minutes=10)  # an auction needs a fair chance to be seen
MAX_DURATION = timedelta(days=30)
MAX_PRICE = 10_000_000  # whole rupees: caps the starting price, the minimum raise and any bid


# Once a bid exists, these are frozen so bidders aren't misled about what they're bidding on.
FROZEN_AFTER_BID = frozenset(
    {"title", "category", "condition", "starting_price", "min_increment", "closes_at"}
)


def sniff_image_ext(data: bytes) -> str | None:
    """Identify the image type from its first bytes, ignoring any client-supplied name or type."""
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _validate_images(images: list[bytes], existing: int = 0) -> list[str]:
    """Check count, size and real type. `existing` is how many photos the listing already has."""
    if existing == 0 and not MIN_IMAGES <= len(images) <= MAX_IMAGES:
        raise ListingError(f"Attach {MIN_IMAGES} to {MAX_IMAGES} photos")
    if existing + len(images) > MAX_IMAGES:
        raise ListingError(f"A listing can have at most {MAX_IMAGES} photos")
    if not images:
        raise ListingError("No photos were uploaded")
    extensions = []
    for data in images:
        if len(data) > MAX_IMAGE_BYTES:
            raise ListingError(f"Each photo must be under {MAX_IMAGE_BYTES // (1024 * 1024)} MB")
        ext = sniff_image_ext(data)
        if ext is None:
            raise ListingError("Photos must be JPEG, PNG or WebP images")
        extensions.append(ext)
    return extensions


def _clean_fields(fields: dict, now: datetime) -> dict:
    """The single set of field rules, used by both create and edit."""
    clean = {}
    for key, value in fields.items():
        if value is None:
            if key == "handover_spot":
                clean[key] = None
                continue
            raise ListingError(f"{key} cannot be empty")
        if key == "title":
            value = value.strip()
            if not value:
                raise ListingError("Title is required")
        elif key == "description":
            value = value.strip()
        elif key == "handover_spot":
            value = value.strip() if isinstance(value, str) else None
            if value and len(value) > 120:
                raise ListingError("Handover spot must be 120 characters or less")
        elif key in ("starting_price", "min_increment"):
            if value < 1:
                raise ListingError("Starting price and minimum increment must be at least 1")
            if value > MAX_PRICE:
                raise ListingError(f"Starting price and minimum increment can be at most {MAX_PRICE}")
        elif key == "closes_at":
            if value.tzinfo is None:
                raise ListingError("closes_at must include a timezone, e.g. 2026-05-01T18:00:00Z")
            if value < now + MIN_DURATION:
                raise ListingError("The auction must run for at least 10 minutes")
            if value > now + MAX_DURATION:
                raise ListingError("The auction can run for at most 30 days")
        clean[key] = value
    return clean


def _write_images(
    listing: Listing, blobs: list[bytes], extensions: list[str], start: int, written: list[Path]
) -> None:
    """Save photo files and attach rows. Every file written is recorded in `written` for cleanup."""
    folder = Path(settings.media_dir) / "listings" / str(listing.id)
    folder.mkdir(parents=True, exist_ok=True)
    for offset, (data, ext) in enumerate(zip(blobs, extensions)):
        name = f"{uuid.uuid4().hex}.{ext}"  # server-chosen name: nothing user-controlled
        path = folder / name
        path.write_bytes(data)
        written.append(path)
        listing.images.append(ListingImage(path=f"listings/{listing.id}/{name}", position=start + offset))


def _discard_files(paths: list[Path]) -> None:
    """Remove files from a failed or finished operation so no orphans are left on disk."""
    for path in paths:
        path.unlink(missing_ok=True)
    for folder in {p.parent for p in paths}:
        try:
            folder.rmdir()  # only succeeds when empty
        except OSError:
            pass


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
    handover_spot: str | None = None,
    now: datetime | None = None,
) -> Listing:
    now = now or utcnow()
    fields = _clean_fields(
        dict(
            title=title,
            category=category,
            condition=condition,
            description=description,
            starting_price=starting_price,
            min_increment=min_increment,
            closes_at=closes_at,
            handover_spot=handover_spot,
        ),
        now,
    )
    extensions = _validate_images(images)

    listing = Listing(seller_id=seller.id, **fields)
    db.add(listing)
    db.flush()  # assigns listing.id, needed for the photo folder name

    written: list[Path] = []
    try:
        _write_images(listing, images, extensions, 0, written)
        db.commit()
    except BaseException:
        db.rollback()
        _discard_files(written)
        raise
    return listing


def update_listing(
    db: Session, listing_id: int, user_id: int, changes: dict, now: datetime | None = None
) -> Listing:
    """Edit fields. Before any bid: anything. After a bid: only the description."""
    now = now or utcnow()
    listing = lock_listing_for_seller(db, listing_id, user_id, now)
    try:
        if listing.leading_bid_id is not None:
            locked = sorted(FROZEN_AFTER_BID & changes.keys())
            if locked:
                raise ListingError(
                    "Bidding has started, so these can no longer be changed: " + ", ".join(locked),
                    "conflict",
                )
        for key, value in _clean_fields(changes, now).items():
            setattr(listing, key, value)
        listing.edited_at = now
        db.commit()
        return listing
    except BaseException:
        db.rollback()
        raise


def add_images(
    db: Session, listing_id: int, user_id: int, blobs: list[bytes], now: datetime | None = None
) -> Listing:
    listing = lock_listing_for_seller(db, listing_id, user_id, now)
    written: list[Path] = []
    try:
        extensions = _validate_images(blobs, existing=len(listing.images))
        start = max((img.position for img in listing.images), default=-1) + 1
        _write_images(listing, blobs, extensions, start, written)
        listing.edited_at = now or utcnow()
        db.commit()
        return listing
    except BaseException:
        db.rollback()
        _discard_files(written)
        raise


def remove_image(
    db: Session, listing_id: int, user_id: int, image_id: int, now: datetime | None = None
) -> Listing:
    listing = lock_listing_for_seller(db, listing_id, user_id, now)
    try:
        image = next((img for img in listing.images if img.id == image_id), None)
        if image is None:
            raise ListingError("Photo not found on this listing", "not_found")
        if len(listing.images) <= MIN_IMAGES:
            raise ListingError(f"A listing needs at least {MIN_IMAGES} photo", "conflict")
        file_path = Path(settings.media_dir) / image.path
        listing.images.remove(image)  # delete-orphan cascade removes the row
        for position, remaining in enumerate(listing.images):
            remaining.position = position  # keep positions contiguous
        listing.edited_at = now or utcnow()
        db.commit()
    except BaseException:
        db.rollback()
        raise
    _discard_files([file_path])  # after commit: if the DB failed, the file must stay
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
        handover_spot=listing.handover_spot,
        edited_at=listing.edited_at,
        extension_count=listing.extension_count,
        images=[f"/media/{img.path}" for img in listing.images],
        image_ids=[img.id for img in listing.images],
        seller=SellerPublic(
            id=listing.seller.id,
            display_name=listing.seller.display_name,
            department=listing.seller.department,
            year_of_study=listing.seller.year_of_study,
        ),
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


def _card(listing: Listing, bid_count: int) -> ListingCard:
    return ListingCard(
        id=listing.id,
        title=listing.title,
        category=listing.category,
        condition=listing.condition,
        status=listing.status,
        starting_price=listing.starting_price,
        current_price=listing.current_price,
        price=listing.current_price if listing.current_price is not None else listing.starting_price,
        bid_count=bid_count,
        closes_at=listing.closes_at,
        thumbnail=f"/media/{listing.images[0].path}" if listing.images else None,
        seller_name=listing.seller.display_name,
        handover_spot=listing.handover_spot,
    )


def search_listings(
    db: Session,
    *,
    q: str | None = None,
    category: Category | None = None,
    condition: Condition | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    closing_soon: bool = False,
    status: ListingStatus | None = ListingStatus.active,  # None = any status
    seller_id: int | None = None,
    sort: Sort = Sort.ending_soon,
    limit: int = 20,
    offset: int = 0,
    now: datetime | None = None,
) -> ListingPage:
    now = now or utcnow()
    # The price a buyer actually faces: the leading bid, or the starting price if no bids yet.
    price = func.coalesce(Listing.current_price, Listing.starting_price)

    conditions = []
    if status is not None:
        conditions.append(Listing.status == status)
    if seller_id is not None:
        conditions.append(Listing.seller_id == seller_id)
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

    items = [_card(listing, count) for listing, count in rows]
    return ListingPage(items=items, total=total, limit=limit, offset=offset, server_time=now)


def my_bids(db: Session, user_id: int) -> list[MyBid]:
    """Every listing this user has bid on, with their best bid and whether they currently lead."""
    rows = db.execute(
        select(Listing, func.max(Bid.amount))
        .join(Bid, Bid.listing_id == Listing.id)
        .where(Bid.bidder_id == user_id)
        .group_by(Listing.id)
        .order_by(Listing.closes_at.desc(), Listing.id.desc())
        .options(selectinload(Listing.images), joinedload(Listing.seller))
    ).all()
    if not rows:
        return []

    ids = [listing.id for listing, _ in rows]
    counts = dict(
        db.execute(select(Bid.listing_id, func.count()).where(Bid.listing_id.in_(ids)).group_by(Bid.listing_id)).all()
    )
    leading_ids = [l.leading_bid_id for l, _ in rows if l.leading_bid_id is not None]
    my_leading = set(
        db.scalars(select(Bid.id).where(Bid.id.in_(leading_ids), Bid.bidder_id == user_id)).all()
    )
    return [
        MyBid(listing=_card(l, counts.get(l.id, 0)), my_highest_bid=top, is_leading=l.leading_bid_id in my_leading)
        for l, top in rows
    ]
