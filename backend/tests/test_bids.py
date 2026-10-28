import threading
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Listing
from tests.conftest import auth_header
from tests.test_listings import create


@pytest.fixture()
def seller_h(client):
    return auth_header(client, email="seller@campus.edu", name="Sam")


@pytest.fixture()
def alice_h(client):
    return auth_header(client, email="alice@campus.edu", name="Alice")


@pytest.fixture()
def bob_h(client):
    return auth_header(client, email="bob@campus.edu", name="Bob")


@pytest.fixture()
def lid(client, seller_h):
    """An active listing: starts at 500, minimum increment 50."""
    r = create(client, seller_h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def bid(client, headers, listing_id, amount):
    return client.post(f"/listings/{listing_id}/bids", json={"amount": amount}, headers=headers)


def test_successful_bid_returns_bid_and_updated_listing(client, lid, alice_h):
    r = bid(client, alice_h, lid, 500)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["bid"]["amount"] == 500 and body["bid"]["bidder_name"] == "Alice"
    assert body["bid"]["is_auto"] is False
    listing = body["listing"]
    assert listing["current_price"] == 500 and listing["bid_count"] == 1
    assert listing["leading_bidder"] == "Alice"
    assert listing["min_next_bid"] == 550  # current price + the 50 increment
    assert "email" not in r.text


def test_bidding_requires_login(client, lid):
    assert client.post(f"/listings/{lid}/bids", json={"amount": 500}).status_code == 401


def test_amount_must_be_a_positive_whole_number(client, lid, alice_h):
    assert bid(client, alice_h, lid, 0).status_code == 422
    assert bid(client, alice_h, lid, -5).status_code == 422
    assert bid(client, alice_h, lid, 500.5).status_code == 422  # no fractions: money is whole rupees
    assert bid(client, alice_h, lid, "lots").status_code == 422
    assert client.post(f"/listings/{lid}/bids", json={}, headers=alice_h).status_code == 422


def test_too_low_tells_the_client_the_minimum(client, lid, alice_h, bob_h):
    first = bid(client, alice_h, lid, 499)
    assert first.status_code == 409
    assert first.json()["detail"] == {"code": "too_low", "message": "Bid must be at least 500", "min_bid": 500}

    bid(client, alice_h, lid, 500)
    second = bid(client, bob_h, lid, 549)  # needs 500 + 50
    assert second.status_code == 409 and second.json()["detail"]["min_bid"] == 550
    assert bid(client, bob_h, lid, 550).status_code == 201


def test_cannot_bid_on_own_listing(client, lid, seller_h):
    r = bid(client, seller_h, lid, 9999)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "own_listing"


def test_unknown_listing(client, alice_h):
    r = bid(client, alice_h, 999, 500)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "not_found"


def test_late_bid_is_refused_even_if_the_closer_never_ran(client, db_session, lid, alice_h):
    listing = db_session.get(Listing, lid)
    listing.closes_at = datetime.now(timezone.utc) - timedelta(seconds=1)  # time is up, status still "active"
    db_session.commit()
    r = bid(client, alice_h, lid, 500)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "closed"
    assert client.get(f"/listings/{lid}/bids").json() == []  # nothing was recorded


def test_cannot_bid_on_a_cancelled_listing(client, lid, seller_h, alice_h):
    client.post(f"/listings/{lid}/cancel", headers=seller_h)
    r = bid(client, alice_h, lid, 500)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "closed"


def test_bid_history_is_public_newest_first_and_names_only(client, lid, alice_h, bob_h):
    assert client.get(f"/listings/{lid}/bids").json() == []  # empty, not an error
    bid(client, alice_h, lid, 500)
    bid(client, bob_h, lid, 550)
    bid(client, alice_h, lid, 600)  # raising your own bid is allowed

    r = client.get(f"/listings/{lid}/bids")  # no auth needed
    assert r.status_code == 200
    rows = r.json()
    assert [(b["bidder_name"], b["amount"]) for b in rows] == [("Alice", 600), ("Bob", 550), ("Alice", 500)]
    assert set(rows[0]) == {"id", "amount", "bidder_name", "created_at", "is_auto"}  # nothing else leaks
    assert "@" not in r.text  # no email addresses anywhere
    assert rows[0]["created_at"].endswith(("Z", "+00:00"))


def test_history_of_unknown_listing_404(client):
    assert client.get("/listings/999/bids").status_code == 404


def test_full_flow_outbid_and_visible_in_listing_browse_and_my_bids(client, lid, alice_h, bob_h):
    bid(client, alice_h, lid, 500)
    bid(client, bob_h, lid, 550)

    detail = client.get(f"/listings/{lid}").json()
    assert detail["leading_bidder"] == "Bob" and detail["current_price"] == 550

    card = client.get("/listings").json()["items"][0]
    assert card["price"] == 550 and card["bid_count"] == 2

    mine = client.get("/me/bids", headers=alice_h).json()
    assert mine[0]["my_highest_bid"] == 500 and mine[0]["is_leading"] is False  # outbid


def test_simultaneous_identical_bids_through_the_whole_stack_only_one_wins(client, lid):
    """8 different users bid 500 at the same instant via real HTTP calls."""
    headers = [auth_header(client, email=f"racer{i}@campus.edu", name=f"Racer{i}") for i in range(8)]
    barrier = threading.Barrier(len(headers))
    codes = []

    def go(h):
        barrier.wait()
        codes.append(bid(client, h, lid, 500).status_code)

    threads = [threading.Thread(target=go, args=(h,)) for h in headers]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert sorted(codes) == [201] + [409] * 7
    assert len(client.get(f"/listings/{lid}/bids").json()) == 1


def test_the_leader_cannot_bid_against_themselves(client, lid, alice_h, bob_h):
    assert bid(client, alice_h, lid, 500).status_code == 201
    r = bid(client, alice_h, lid, 600)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "already_leading"
    assert len(client.get(f"/listings/{lid}/bids").json()) == 1
    bid(client, bob_h, lid, 550)
    assert bid(client, alice_h, lid, 600).status_code == 201  # allowed again once Bob leads


def test_bid_amount_has_an_upper_cap(client, lid, alice_h):
    assert bid(client, alice_h, lid, 10_000_001).status_code == 422
