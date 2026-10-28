"""Market analytics service: fast-moving products, category trends, and student interest radar."""

import collections
import re
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.clock import utcnow
from app.models import Bid, Category, Listing, ListingImage, ListingStatus, Want
from app.schemas.analytics import CategoryTrend, FastMovingItem, MarketPulse, StudentInterest

CATEGORY_LABELS = {
    Category.cycle: "Cycles",
    Category.calculator: "Calculators",
    Category.books: "Books & Notes",
    Category.electronics: "Electronics & Gadgets",
    Category.furniture: "Dorm Furniture",
    Category.other: "Other Gear",
}

SOLD_STATUSES = (
    ListingStatus.completed,
    ListingStatus.reserved,
    ListingStatus.pending_approval,
)

CLOSED_UNSOLD = (
    ListingStatus.unsold,
    ListingStatus.cancelled,
    ListingStatus.rejected,
    ListingStatus.failed_pickup,
)


def _to_fast_moving_item(listing: Listing, bid_count: int) -> FastMovingItem:
    photo = f"/media/{listing.images[0].path}" if listing.images else None  # a ready-made URL, like every other card's thumbnail
    start = listing.starting_price
    curr = listing.current_price or start
    growth = round(((curr - start) / start) * 100, 1) if start > 0 else 0.0
    is_hot = bid_count >= 2 or (bid_count >= 1 and growth > 0)
    return FastMovingItem(
        id=listing.id,
        title=listing.title,
        category=listing.category,
        condition=listing.condition,
        starting_price=listing.starting_price,
        current_price=listing.current_price,
        bid_count=bid_count,
        closes_at=listing.closes_at,
        photo=photo,
        price_growth_pct=growth,
        status=listing.status.value,
        is_hot=is_hot,
    )


def get_market_pulse(db: Session, now: datetime | None = None) -> MarketPulse:
    now = now or utcnow()

    # 1. Total statistics
    total_active = db.scalar(
        select(func.count()).select_from(Listing).where(Listing.status == ListingStatus.active)
    ) or 0
    total_completed = db.scalar(
        select(func.count()).select_from(Listing).where(Listing.status.in_(SOLD_STATUSES))
    ) or 0
    total_closed_unsuccessful = db.scalar(
        select(func.count()).select_from(Listing).where(Listing.status.in_(CLOSED_UNSOLD))
    ) or 0
    total_bids = db.scalar(select(func.count()).select_from(Bid)) or 0

    volume = db.scalar(
        select(func.sum(Listing.current_price)).where(
            Listing.status.in_(SOLD_STATUSES), Listing.current_price.is_not(None)
        )
    ) or 0

    total_concluded = total_completed + total_closed_unsuccessful
    overall_sell_through = (
        round((total_completed / total_concluded) * 100, 1) if total_concluded > 0 else 0.0
    )

    # 2. Fast-moving items: active items with bids or closing soonest
    bid_count_sub = (
        select(func.count()).where(Bid.listing_id == Listing.id).correlate(Listing).scalar_subquery()
    )

    active_rows = db.execute(
        select(Listing, bid_count_sub)
        .where(Listing.status == ListingStatus.active)
        .order_by(bid_count_sub.desc(), Listing.closes_at.asc())
        .limit(8)
        .options(selectinload(Listing.images))
    ).all()

    fast_moving = [_to_fast_moving_item(listing, count) for listing, count in active_rows]

    # 3. Recent successful sales with competitive bids
    recent_sales_rows = db.execute(
        select(Listing, bid_count_sub)
        .where(Listing.status.in_(SOLD_STATUSES))
        .order_by(Listing.updated_at.desc())
        .limit(6)
        .options(selectinload(Listing.images))
    ).all()

    recent_successful_sales = [
        _to_fast_moving_item(listing, count) for listing, count in recent_sales_rows
    ]

    # 4. Category trends based on bids and sales
    category_trends: list[CategoryTrend] = []
    for cat in Category:
        cat_total = db.scalar(
            select(func.count()).select_from(Listing).where(Listing.category == cat)
        ) or 0
        cat_active = db.scalar(
            select(func.count())
            .select_from(Listing)
            .where(Listing.category == cat, Listing.status == ListingStatus.active)
        ) or 0
        cat_sold = db.scalar(
            select(func.count())
            .select_from(Listing)
            .where(Listing.category == cat, Listing.status.in_(SOLD_STATUSES))
        ) or 0
        cat_unsuccessful = db.scalar(
            select(func.count())
            .select_from(Listing)
            .where(Listing.category == cat, Listing.status.in_(CLOSED_UNSOLD))
        ) or 0
        cat_bids = db.scalar(
            select(func.count())
            .select_from(Bid)
            .join(Listing, Bid.listing_id == Listing.id)
            .where(Listing.category == cat)
        ) or 0

        avg_price = db.scalar(
            select(func.avg(Listing.current_price)).where(
                Listing.category == cat,
                Listing.status.in_(SOLD_STATUSES),
                Listing.current_price.is_not(None),
            )
        )

        closed = cat_sold + cat_unsuccessful
        if closed > 0:
            rate = round((cat_sold / closed) * 100, 1)
        elif cat_active > 0 and cat_bids > 0:
            rate = round(min(100.0, (cat_bids / cat_active) * 50), 1)
        else:
            rate = 0.0

        avg_bids = round(cat_bids / cat_total, 1) if cat_total > 0 else 0.0

        if rate >= 50 or avg_bids >= 2:
            badge = "High demand"
        elif cat_bids > 0 or cat_active >= 2:
            badge = "Active"
        elif cat_total > 0:
            badge = "Steady"
        else:
            badge = "Emerging"

        category_trends.append(
            CategoryTrend(
                category=cat.value,
                label=CATEGORY_LABELS.get(cat, cat.value.capitalize()),
                total_listings=cat_total,
                active_listings=cat_active,
                completed_sales=cat_sold,
                total_bids=cat_bids,
                avg_bids_per_item=avg_bids,
                sell_through_rate=rate,
                avg_sale_price=round(avg_price) if avg_price else None,
                demand_badge=badge,
            )
        )

    # Sort categories by total bids & sell through rate
    category_trends.sort(key=lambda c: (c.total_bids, c.sell_through_rate, c.active_listings), reverse=True)

    # 5. Student Interests: analyzed from saved Wants and search patterns
    wants_records = db.execute(select(Want)).scalars().all()
    keyword_counter = collections.Counter()
    cat_wants_counter = collections.Counter()

    for w in wants_records:
        if w.category:
            cat_wants_counter[w.category.value] += 1
        words = [word.strip() for word in re.split(r"\s+", (w.keywords or "").lower()) if len(word.strip()) >= 3]
        for word in words:
            keyword_counter[word] += 1

    student_interests: list[StudentInterest] = []
    # If student wants exist, build real insights
    for word, count in keyword_counter.most_common(6):
        # Check active listings matching this word
        match_count = db.scalar(
            select(func.count())
            .select_from(Listing)
            .where(
                Listing.status == ListingStatus.active,
                or_(
                    Listing.title.ilike(f"%{word}%"),
                    Listing.description.ilike(f"%{word}%"),
                ),
            )
        ) or 0
        student_interests.append(
            StudentInterest(
                keyword=word.capitalize(),
                category=None,
                wants_count=count,
                active_listings_count=match_count,
                unfilled_demand=count > match_count,
            )
        )

    # If no or few explicit keyword wants saved yet, seed with top high-demand campus essentials
    if len(student_interests) < 4:
        seed_items = [
            ("Scientific Calculator", "calculator"),
            ("Campus Cycle", "cycle"),
            ("Engineering Mathematics", "books"),
            ("Laptop Stand & Keyboard", "electronics"),
        ]
        for name, cat_str in seed_items:
            if not any(si.keyword.lower() == name.lower() for si in student_interests):
                match_count = db.scalar(
                    select(func.count())
                    .select_from(Listing)
                    .where(Listing.status == ListingStatus.active, Listing.category == Category(cat_str))
                ) or 0
                bid_count = db.scalar(
                    select(func.count())
                    .select_from(Bid)
                    .join(Listing, Bid.listing_id == Listing.id)
                    .where(Listing.category == Category(cat_str))
                ) or 0
                wants_cnt = max(1, bid_count, cat_wants_counter.get(cat_str, 0))
                student_interests.append(
                    StudentInterest(
                        keyword=name,
                        category=cat_str,
                        wants_count=wants_cnt,
                        active_listings_count=match_count,
                        unfilled_demand=match_count <= 1,
                    )
                )

    return MarketPulse(
        total_active_listings=total_active,
        total_completed_sales=total_completed,
        total_volume_traded=int(volume),
        total_bids_placed=total_bids,
        overall_sell_through_rate=overall_sell_through,
        fast_moving=fast_moving,
        category_trends=category_trends,
        student_interests=student_interests,
        recent_successful_sales=recent_successful_sales,
    )
