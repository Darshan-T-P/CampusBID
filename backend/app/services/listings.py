"""Creating and presenting listings. Bidding and closing rules live in auction.py."""

import enum
import difflib
import hashlib
import io
import re
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageOps
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.clock import utcnow
from app.core.config import settings
from app.models import Bid, Category, Condition, Listing, ListingImage, ListingStatus, User, Watch
from app.schemas.listing import ListingCard, ListingDetail, ListingPage, MyBid, SellerPublic
from app.services.auction import lock_listing_for_seller, min_valid_bid
from app.services import wants
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
            value = value or None  # clearing the field (or only spaces) means "no spot", not an empty string
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


MAX_IMAGE_DIMENSION = 1280


def _optimize_image(data: bytes, ext: str) -> bytes:
    """Downscales images exceeding MAX_IMAGE_DIMENSION and re-encodes with optimized compression.
    If image decoding fails (e.g. truncated or synthetic mock bytes), returns data untouched.
    """
    try:
        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im)
            if max(im.width, im.height) > MAX_IMAGE_DIMENSION:
                im.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            if ext in ("jpg", "jpeg"):
                if im.mode not in ("RGB", "L"):
                    im = im.convert("RGB")
                im.save(out, format="JPEG", quality=85, optimize=True)
            elif ext == "png":
                im.save(out, format="PNG", optimize=True)
            elif ext == "webp":
                im.save(out, format="WEBP", quality=85, method=4)
            else:
                return data
            return out.getvalue()
    except Exception:
        return data


def _write_images(
    listing: Listing, blobs: list[bytes], extensions: list[str], start: int, written: list[Path]
) -> None:
    """Save photo files and attach rows. Every file written is recorded in `written` for cleanup."""
    folder = Path(settings.media_dir) / "listings" / str(listing.id)
    folder.mkdir(parents=True, exist_ok=True)
    for offset, (data, ext) in enumerate(zip(blobs, extensions)):
        name = f"{uuid.uuid4().hex}.{ext}"  # server-chosen name: nothing user-controlled
        path = folder / name
        optimized = _optimize_image(data, ext)
        path.write_bytes(optimized)
        written.append(path)
        listing.images.append(
            ListingImage(path=f"listings/{listing.id}/{name}", position=start + offset, sha256=hashlib.sha256(optimized).hexdigest())
        )


def _discard_files(paths: list[Path]) -> None:
    """Remove files from a failed or finished operation so no orphans are left on disk."""
    for path in paths:
        path.unlink(missing_ok=True)
    for folder in {p.parent for p in paths}:
        try:
            folder.rmdir()  # only succeeds when empty
        except OSError:
            pass


class DuplicateListing(ListingError):
    """The seller already has a live listing that looks like this one. They can confirm it is a second item."""

    def __init__(self, existing: Listing, reason: str):
        what = {
            "photo": f"One of these photos is already on your open listing \"{existing.title}\".",
            "title": f"You already have an open listing called \"{existing.title}\".",
            "similar": f"You already have a very similar open listing, \"{existing.title}\".",
        }[reason]
        super().__init__(what, "conflict")
        self.existing = existing
        self.reason = reason


_LIVE = (ListingStatus.active, ListingStatus.pending_approval, ListingStatus.reserved)


def _normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def find_possible_duplicate(
    db: Session, seller_id: int, title: str, category: Category, blobs: list[bytes], extensions: list[str]
) -> DuplicateListing | None:
    """Does this seller already have a LIVE listing that looks like the one they are posting?

    Same photo (by file fingerprint), the same title once case and punctuation are ignored, or a near-identical title in
    the same category. Cancelled, unsold and finished listings don't count: re-listing those is normal.
    """
    mine = db.scalars(
        select(Listing).where(Listing.seller_id == seller_id, Listing.status.in_(_LIVE)).options(selectinload(Listing.images))
    ).all()
    # Compared the way they are stored: after the same optimisation, so a photo posted twice gives the same fingerprint.
    fingerprints = {hashlib.sha256(_optimize_image(b, ext)).hexdigest() for b, ext in zip(blobs, extensions)}
    wanted = _normalize_title(title)
    for existing in mine:
        if any(image.sha256 in fingerprints for image in existing.images if image.sha256):
            return DuplicateListing(existing, "photo")
    for existing in mine:
        theirs = _normalize_title(existing.title)
        if theirs == wanted:
            return DuplicateListing(existing, "title")
        if existing.category == category and difflib.SequenceMatcher(None, theirs, wanted).ratio() >= 0.85:
            return DuplicateListing(existing, "similar")
    return None


def backfill_image_fingerprints(db: Session) -> int:
    """Give photos uploaded before fingerprints existed one, read from the stored file. Run at startup; cheap when
    there is nothing to do. Returns how many were filled in."""
    rows = db.scalars(select(ListingImage).where(ListingImage.sha256.is_(None)).limit(2000)).all()
    done = 0
    for image in rows:
        path = Path(settings.media_dir) / image.path
        try:
            image.sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
            done += 1
        except OSError:
            continue  # the file is gone: nothing to fingerprint
    if done:
        db.commit()
    return done


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
    confirm_duplicate: bool = False,
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
    open_now = db.scalar(
        select(func.count()).select_from(Listing).where(Listing.seller_id == seller.id, Listing.status == ListingStatus.active)
    )
    if open_now >= settings.max_open_listings:
        raise ListingError(
            f"You can have up to {settings.max_open_listings} auctions open at once. Cancel one, or wait for one to end.", "conflict"
        )
    if not confirm_duplicate:
        duplicate = find_possible_duplicate(db, seller.id, fields["title"], fields["category"], images, extensions)
        if duplicate is not None:
            raise duplicate

    listing = Listing(seller_id=seller.id, **fields)
    db.add(listing)
    db.flush()  # assigns listing.id, needed for the photo folder name
    wants.notify_matches(db, listing)  # students who saved a matching alert hear about it (same transaction)

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


_LEGACY_AMOUNT = re.compile(r"(winning bid of |sale completed at |approved by the seller at )(\d+)", re.IGNORECASE)


def format_outcome_note(note: str | None) -> str | None:
    """Notes written before rupee signs were added say "winning bid of 2800". Show every note the same way
    ("₹2,800") without rewriting what is stored. Already-formatted notes are left alone."""
    if not note:
        return note
    return _LEGACY_AMOUNT.sub(lambda m: f"{m.group(1)}₹{int(m.group(2)):,}", note)


def seller_record(db: Session, seller: User, now: datetime) -> SellerPublic:
    """The seller's public details plus a small track record (counts only, nothing about buyers)."""
    by_status = dict(
        db.execute(select(Listing.status, func.count()).where(Listing.seller_id == seller.id).group_by(Listing.status)).all()
    )
    open_now = db.scalar(
        select(func.count()).select_from(Listing).where(
            Listing.seller_id == seller.id, Listing.status == ListingStatus.active, Listing.closes_at > now
        )
    )
    return SellerPublic(
        id=seller.id,
        display_name=seller.display_name,
        department=seller.department,
        year_of_study=seller.year_of_study,
        member_since=seller.created_at,
        items_sold=by_status.get(ListingStatus.completed, 0),
        listed=sum(n for status, n in by_status.items() if status != ListingStatus.cancelled),
        open_now=open_now,
    )


def listing_detail(db: Session, listing: Listing, now: datetime | None = None) -> ListingDetail:
    now = now or utcnow()
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
        outcome_note=format_outcome_note(listing.outcome_note),
        handover_spot=listing.handover_spot,
        edited_at=listing.edited_at,
        extension_count=listing.extension_count,
        watchers=watch_counts(db, [listing.id]).get(listing.id, 0),
        images=[f"/media/{img.path}" for img in listing.images],
        image_ids=[img.id for img in listing.images],
        seller=seller_record(db, listing.seller, now),
        created_at=listing.created_at,
        server_time=now,
    )


class Sort(str, enum.Enum):
    ending_soon = "ending_soon"
    newest = "newest"
    price_low = "price_low"
    price_high = "price_high"


def _escape_like(term: str) -> str:
    """Make %, _ and \\ literal so a search for "50%" isn't a wildcard."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def watch_counts(db: Session, listing_ids: list[int]) -> dict[int, int]:
    """How many students watch each of these auctions (counts only)."""
    if not listing_ids:
        return {}
    return dict(
        db.execute(select(Watch.listing_id, func.count()).where(Watch.listing_id.in_(listing_ids)).group_by(Watch.listing_id)).all()
    )


def _card(listing: Listing, bid_count: int, watchers: int = 0) -> ListingCard:
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
        seller_id=listing.seller_id,
        seller_name=listing.seller.display_name,
        handover_spot=listing.handover_spot,
        watchers=watchers,
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
    watching = select(func.count()).where(Watch.listing_id == Listing.id).correlate(Listing).scalar_subquery()
    rows = db.execute(
        select(Listing, bid_count, watching)
        .where(*conditions)
        .order_by(*order_by)
        .limit(limit)
        .offset(offset)
        .options(selectinload(Listing.images), joinedload(Listing.seller))
    ).all()

    items = [_card(listing, count, watchers) for listing, count, watchers in rows]
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
    watching = watch_counts(db, ids)
    leading_ids = [l.leading_bid_id for l, _ in rows if l.leading_bid_id is not None]
    my_leading = set(
        db.scalars(select(Bid.id).where(Bid.id.in_(leading_ids), Bid.bidder_id == user_id)).all()
    )
    return [
        MyBid(listing=_card(l, counts.get(l.id, 0), watching.get(l.id, 0)), my_highest_bid=top, is_leading=l.leading_bid_id in my_leading)
        for l, top in rows
    ]


def delete_listing(db: Session, listing_id: int, user_id: int) -> None:
    """Permanently deletes a listing that has no bids. If it has bids, raise error telling user to cancel."""
    listing = db.get(Listing, listing_id)
    if listing is None:
        raise ListingError("Listing not found", "not_found")
    if listing.seller_id != user_id:
        raise ListingError("Only the seller can delete this listing", "forbidden")

    # Check if there are any bids
    has_bids = db.scalar(select(func.count()).select_from(Bid).where(Bid.listing_id == listing_id)) > 0
    if has_bids:
        raise ListingError("Auctions with placed bids cannot be permanently deleted. You can cancel it instead.", "has_bids")

    if listing.status in (ListingStatus.pending_approval, ListingStatus.reserved, ListingStatus.completed):
        raise ListingError("Sales in progress or completed cannot be deleted.", "conflict")

    # Remove photo folder from disk
    folder = Path(settings.media_dir) / "listings" / str(listing.id)
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)

    # Delete related dependent rows
    from app.models import Notification, Watch
    from app.models.question import ListingQuestion
    db.execute(delete(Watch).where(Watch.listing_id == listing_id))
    db.execute(delete(ListingQuestion).where(ListingQuestion.listing_id == listing_id))
    db.execute(delete(Notification).where(Notification.listing_id == listing_id))
    db.delete(listing)
    db.commit()
