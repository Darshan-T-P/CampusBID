"""Creating and presenting listings. Bidding and closing rules live in auction.py."""

import shutil
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.config import settings
from app.models import Bid, Category, Condition, Listing, ListingImage, ListingStatus, User
from app.schemas.listing import ListingDetail, SellerPublic
from app.services.auction import min_valid_bid

MIN_IMAGES = 1
MAX_IMAGES = 5
MAX_IMAGE_BYTES = 5 * 1024 * 1024


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
