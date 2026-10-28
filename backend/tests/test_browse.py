from datetime import datetime, timedelta, timezone

import pytest

from app.models import Category, Condition, Listing, ListingImage, ListingStatus, User
from app.services.auction import place_bid

NOW = datetime.now(timezone.utc)


@pytest.fixture()
def seller(db_session):
    user = User(email="seller@campus.edu", password_hash="x", display_name="Sam")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture()
def bidder(db_session):
    user = User(email="bidder@campus.edu", password_hash="x", display_name="Bea")
    db_session.add(user)
    db_session.commit()
    return user


def add(db, seller, title, *, category=Category.other, condition=Condition.good, start=100,
        closes_in=timedelta(hours=5), description="", status=ListingStatus.active, created_ago=0):
    listing = Listing(
        seller_id=seller.id,
        title=title,
        category=category,
        condition=condition,
        description=description,
        starting_price=start,
        closes_at=NOW + closes_in,
        status=status,
        created_at=NOW - timedelta(minutes=created_ago),
    )
    db.add(listing)
    db.commit()
    return listing


def titles(client, **params):
    r = client.get("/listings", params=params)
    assert r.status_code == 200, r.text
    return [item["title"] for item in r.json()["items"]]


def test_browse_is_public_and_lists_open_auctions(client, db_session, seller):
    add(db_session, seller, "Cycle")
    r = client.get("/listings")  # no auth
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1 and body["limit"] == 20 and body["offset"] == 0
    card = body["items"][0]
    assert card["title"] == "Cycle" and card["seller_name"] == "Sam"
    assert "email" not in r.text


def test_default_view_hides_closed_cancelled_and_expired(client, db_session, seller):
    add(db_session, seller, "Open")
    add(db_session, seller, "Cancelled", status=ListingStatus.cancelled)
    add(db_session, seller, "Sold", status=ListingStatus.pending_approval)
    # Still marked active, but its time is up and the background closer hasn't run yet.
    add(db_session, seller, "Expired not swept", closes_in=timedelta(minutes=-1))
    assert titles(client) == ["Open"]


def test_status_filter_shows_other_states(client, db_session, seller):
    add(db_session, seller, "Open")
    add(db_session, seller, "Cancelled", status=ListingStatus.cancelled)
    assert titles(client, status="cancelled") == ["Cancelled"]


def test_search_matches_title_or_description_case_insensitively(client, db_session, seller):
    add(db_session, seller, "Hero Honda Cycle")
    add(db_session, seller, "Calculator", description="Casio fx-991, works with any CYCLE of exams")
    add(db_session, seller, "Textbook")
    assert sorted(titles(client, q="cycle")) == ["Calculator", "Hero Honda Cycle"]


def test_search_requires_every_word_in_any_order(client, db_session, seller):
    add(db_session, seller, "Hero Honda Cycle")
    add(db_session, seller, "Racing Cycle")
    assert titles(client, q="cycle hero") == ["Hero Honda Cycle"]


def test_search_wildcards_are_literal(client, db_session, seller):
    add(db_session, seller, "Cycle")
    add(db_session, seller, "50% off notes")
    add(db_session, seller, "snake_case book")
    assert titles(client, q="%") == ["50% off notes"]  # not "match everything"
    assert titles(client, q="_") == ["snake_case book"]


def test_category_and_condition_filters(client, db_session, seller):
    add(db_session, seller, "Cycle", category=Category.cycle, condition=Condition.good)
    add(db_session, seller, "Casio", category=Category.calculator, condition=Condition.new)
    add(db_session, seller, "Old cycle", category=Category.cycle, condition=Condition.poor)
    assert sorted(titles(client, category="cycle")) == ["Cycle", "Old cycle"]
    assert titles(client, category="cycle", condition="poor") == ["Old cycle"]
    assert client.get("/listings", params={"category": "spaceship"}).status_code == 422


def test_price_filter_uses_current_bid_not_starting_price(client, db_session, seller, bidder):
    cheap = add(db_session, seller, "Cheap", start=100)
    add(db_session, seller, "Pricey", start=900)
    assert titles(client, max_price=500) == ["Cheap"]
    # A bid lifts "Cheap" above the cap, so it must drop out of the filter.
    place_bid(db_session, cheap.id, bidder.id, 600)
    assert titles(client, max_price=500) == []
    assert sorted(titles(client, min_price=600)) == ["Cheap", "Pricey"]


def test_min_price_above_max_price_is_rejected(client):
    assert client.get("/listings", params={"min_price": 500, "max_price": 100}).status_code == 422


def test_closing_soon_window_is_24_hours(client, db_session, seller):
    add(db_session, seller, "In 30 min", closes_in=timedelta(minutes=30))
    add(db_session, seller, "In 20 hours", closes_in=timedelta(hours=20))
    add(db_session, seller, "In 2 days", closes_in=timedelta(days=2))
    assert sorted(titles(client, closing_soon="true")) == ["In 20 hours", "In 30 min"]


def test_sort_orders(client, db_session, seller):
    add(db_session, seller, "B", start=300, closes_in=timedelta(hours=2), created_ago=10)
    add(db_session, seller, "A", start=500, closes_in=timedelta(hours=1), created_ago=30)
    add(db_session, seller, "C", start=100, closes_in=timedelta(hours=3), created_ago=5)
    assert titles(client) == ["A", "B", "C"]  # ending_soon is the default
    assert titles(client, sort="newest") == ["C", "B", "A"]
    assert titles(client, sort="price_low") == ["C", "B", "A"]
    assert titles(client, sort="price_high") == ["A", "B", "C"]


def test_pagination_covers_everything_once(client, db_session, seller):
    for i in range(5):
        add(db_session, seller, f"Item {i}", closes_in=timedelta(hours=1 + i))
    page1 = client.get("/listings", params={"limit": 2, "offset": 0}).json()
    page2 = client.get("/listings", params={"limit": 2, "offset": 2}).json()
    page3 = client.get("/listings", params={"limit": 2, "offset": 4}).json()
    assert page1["total"] == page2["total"] == page3["total"] == 5
    seen = [i["title"] for p in (page1, page2, page3) for i in p["items"]]
    assert seen == [f"Item {i}" for i in range(5)]
    assert client.get("/listings", params={"limit": 0}).status_code == 422
    assert client.get("/listings", params={"limit": 51}).status_code == 422


def test_card_shows_bid_count_price_and_thumbnail(client, db_session, seller, bidder):
    listing = add(db_session, seller, "Cycle", start=100)
    db_session.add(ListingImage(listing_id=listing.id, path="listings/1/a.png", position=0))
    db_session.add(ListingImage(listing_id=listing.id, path="listings/1/b.png", position=1))
    db_session.commit()

    card = client.get("/listings").json()["items"][0]
    assert card["price"] == 100 and card["current_price"] is None and card["bid_count"] == 0
    assert card["thumbnail"] == "/media/listings/1/a.png"  # first photo

    place_bid(db_session, listing.id, bidder.id, 150)
    card = client.get("/listings").json()["items"][0]
    assert card["price"] == 150 and card["bid_count"] == 1
