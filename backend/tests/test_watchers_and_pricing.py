"""The "N watching" counter and price suggestions from real past sales."""

import asyncio
from datetime import timedelta

import pytest

from app.core.clock import utcnow
from app.core.events import broadcaster
from app.models import Condition, Listing, ListingStatus
from app.services import pricing
from tests.conftest import auth_header
from tests.test_listings import create


@pytest.fixture()
def sam(client):
    return auth_header(client, email="seller@campus.edu", name="Sam")


def student(client, n):
    return auth_header(client, email=f"s{n}@campus.edu", name=f"S{n}")


# --- N watching -----------------------------------------------------------------------------------------


def test_the_count_is_on_the_auction_and_on_its_card(client, sam):
    lid = create(client, sam).json()["id"]
    assert client.get(f"/listings/{lid}").json()["watchers"] == 0
    for n in range(3):
        client.put(f"/listings/{lid}/watch", headers=student(client, n))
    assert client.get(f"/listings/{lid}").json()["watchers"] == 3
    assert client.get("/listings").json()["items"][0]["watchers"] == 3


def test_it_goes_down_when_someone_unsaves_and_ignores_repeat_saves(client, sam):
    lid = create(client, sam).json()["id"]
    a, b = student(client, 1), student(client, 2)
    client.put(f"/listings/{lid}/watch", headers=a)
    client.put(f"/listings/{lid}/watch", headers=a)  # saving twice is still one watcher
    client.put(f"/listings/{lid}/watch", headers=b)
    assert client.get(f"/listings/{lid}").json()["watchers"] == 2
    client.delete(f"/listings/{lid}/watch", headers=a)
    assert client.get(f"/listings/{lid}").json()["watchers"] == 1


def test_it_is_only_a_number_never_who(client, sam):
    lid = create(client, sam).json()["id"]
    client.put(f"/listings/{lid}/watch", headers=student(client, 1))
    text = client.get(f"/listings/{lid}").text + client.get("/listings").text
    assert "s1@campus.edu" not in text and '"watchers"' in text


def test_every_list_that_shows_cards_has_the_count(client, sam):
    lid = create(client, sam).json()["id"]
    fan = student(client, 1)
    client.put(f"/listings/{lid}/watch", headers=fan)
    client.post(f"/listings/{lid}/bids", json={"amount": 500}, headers=fan)
    assert client.get("/me/watchlist", headers=fan).json()[0]["watchers"] == 1
    assert client.get("/me/bids", headers=fan).json()[0]["listing"]["watchers"] == 1
    assert client.get("/me/listings", headers=sam).json()["items"][0]["watchers"] == 1


def test_watching_and_unwatching_are_pushed_to_everyone_on_the_page(client, sam):
    lid = create(client, sam).json()["id"]
    loop = asyncio.new_event_loop()
    q = loop.run_until_complete(broadcaster.subscribe(lid))
    fan = student(client, 1)
    client.put(f"/listings/{lid}/watch", headers=fan)
    first = loop.run_until_complete(asyncio.wait_for(q.get(), 2))
    client.delete(f"/listings/{lid}/watch", headers=fan)
    second = loop.run_until_complete(asyncio.wait_for(q.get(), 2))
    loop.close()
    assert first["event"] == "watchers" and first["data"] == {"listing_id": lid, "count": 1}
    assert second["data"]["count"] == 0


# --- price suggestions ----------------------------------------------------------------------------------


def sold(db, seller_id, title, price, category="cycle", condition="good", status=ListingStatus.completed, days_ago=10):
    db.add(Listing(
        seller_id=seller_id, title=title, category=category, condition=Condition(condition), starting_price=100,
        current_price=price, closes_at=utcnow() - timedelta(days=days_ago), status=status,
    ))
    db.commit()


def suggestion(client, headers, **params):
    return client.get("/pricing/suggestion", params=params, headers=headers)


def test_with_too_few_sales_it_says_so_instead_of_guessing(client, db_session, sam):
    sold(db_session, 1, "Hero cycle", 2000)
    sold(db_session, 1, "Hercules cycle", 2400)
    r = suggestion(client, sam, category="cycle")
    assert r.status_code == 200 and r.json() == {"count": 2, "basis": None, "low": None, "median": None, "high": None, "suggested_start": None}


def test_similar_items_come_first(client, db_session, sam):
    for price in (1800, 2000, 2200, 2600):
        sold(db_session, 1, f"Hero Sprint cycle {price}", price)
    for price in (5000, 5200, 6000):
        sold(db_session, 1, "Firefox mountain bike", price)
    r = suggestion(client, sam, category="cycle", title="Hero Sprint 21 speed").json()
    assert r["basis"] == "similar" and r["count"] == 4
    assert (r["low"], r["median"], r["high"]) == (2000, 2100, 2200)  # the mountain bikes are not "similar"
    assert r["suggested_start"] == 1450  # 70% of the median 2100 is 1470, rounded to a tidy 50


def test_it_falls_back_to_condition_then_to_the_whole_category(client, db_session, sam):
    for price in (900, 1000, 1100):
        sold(db_session, 1, "Plain bike", price, condition="fair")
    sold(db_session, 1, "Another bike", 4000, condition="new")
    r = suggestion(client, sam, category="cycle", condition="fair", title="zzz unmatched words").json()
    assert r["basis"] == "condition" and r["count"] == 3 and r["median"] == 1000
    r = suggestion(client, sam, category="cycle", condition="like_new").json()  # no like-new sales: use the category
    assert r["basis"] == "category" and r["count"] == 4


def test_only_real_recent_sales_in_that_category_count(client, db_session, sam):
    for price in (800, 900, 1000):
        sold(db_session, 1, "Casio calculator", price, category="calculator")
    sold(db_session, 1, "Old cycle", 3000, status=ListingStatus.unsold)  # never sold
    sold(db_session, 1, "Cancelled cycle", 3000, status=ListingStatus.cancelled)
    sold(db_session, 1, "Ancient cycle", 3000, days_ago=400)  # too old
    assert suggestion(client, sam, category="cycle").json()["count"] == 0  # unsold, cancelled and ancient ones don't count
    assert suggestion(client, sam, category="calculator").json()["count"] == 3


def test_sales_waiting_for_approval_or_handover_count_as_sold(client, db_session, sam):
    for status in (ListingStatus.pending_approval, ListingStatus.reserved, ListingStatus.completed):
        sold(db_session, 1, "Hero cycle", 2000, status=status)
    assert suggestion(client, sam, category="cycle", title="hero").json()["count"] == 3


def test_it_needs_login_and_a_valid_category(client, sam):
    assert client.get("/pricing/suggestion?category=cycle").status_code == 401
    assert suggestion(client, sam, category="spaceship").status_code == 422
    assert suggestion(client, sam).status_code == 422


def test_it_reveals_nothing_about_people(client, db_session, sam):
    for price in (1000, 1100, 1200):
        sold(db_session, 1, "Hero cycle", price)
    body = suggestion(client, sam, category="cycle").text
    assert "Sam" not in body and "seller" not in body.lower() and "@" not in body


def test_the_start_is_never_below_fifty_rupees():
    assert pricing._summary([40, 60, 80], "category").suggested_start == 50
