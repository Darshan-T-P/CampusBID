"""The on-campus handover spot: where buyer and seller meet. Optional, public, editable, told to the winner."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import Notification, User
from app.services.auction import close_due_listings, place_bid
from tests.conftest import auth_header
from tests.test_listings import PNG, future


@pytest.fixture()
def seller_h(client):
    return auth_header(client, email="seller@campus.edu", name="Sam")


def make(client, headers, **overrides):
    data = {"title": "Hero cycle", "category": "cycle", "condition": "good", "starting_price": "500",
            "min_increment": "50", "closes_at": future(), **overrides}
    return client.post("/listings", data={k: v for k, v in data.items() if v is not None}, files=[("images", ("a.png", PNG, "image/png"))], headers=headers)


def patch(client, headers, lid, **body):
    return client.patch(f"/listings/{lid}", json=body, headers=headers)


# --- creating ---------------------------------------------------------------


def test_a_listing_can_be_created_with_a_handover_spot(client, seller_h):
    r = make(client, seller_h, handover_spot="Central Library Gate")
    assert r.status_code == 201 and r.json()["handover_spot"] == "Central Library Gate"


def test_the_spot_is_optional(client, seller_h):
    r = make(client, seller_h)
    assert r.status_code == 201 and r.json()["handover_spot"] is None


def test_the_spot_is_trimmed_and_blank_means_none(client, seller_h):
    assert make(client, seller_h, handover_spot="  Main Canteen  ").json()["handover_spot"] == "Main Canteen"
    assert make(client, seller_h, handover_spot="   ").json()["handover_spot"] is None


def test_a_spot_over_120_characters_is_refused(client, seller_h):
    assert make(client, seller_h, handover_spot="x" * 121).status_code == 422
    assert make(client, seller_h, handover_spot="x" * 120).status_code == 201


# --- editing ----------------------------------------------------------------


def test_the_spot_can_be_changed_and_marks_the_listing_edited(client, seller_h):
    lid = make(client, seller_h, handover_spot="Main Canteen").json()["id"]
    r = patch(client, seller_h, lid, handover_spot="Hostel Block A")
    assert r.status_code == 200 and r.json()["handover_spot"] == "Hostel Block A"
    assert r.json()["edited_at"] is not None  # buyers can see the listing changed


def test_clearing_the_spot_stores_nothing_not_an_empty_string(client, db_session, seller_h):
    from app.models import Listing

    lid = make(client, seller_h, handover_spot="Main Canteen").json()["id"]
    for cleared in (None, "", "   "):
        patch(client, seller_h, lid, handover_spot="Main Canteen")
        r = patch(client, seller_h, lid, handover_spot=cleared)
        assert r.status_code == 200 and r.json()["handover_spot"] is None, repr(cleared)
        db_session.expire_all()
        assert db_session.get(Listing, lid).handover_spot is None  # really NULL in the database


def test_the_spot_stays_editable_after_bidding_starts_unlike_the_price(client, db_session, seller_h):
    lid = make(client, seller_h, handover_spot="Main Canteen").json()["id"]
    bidder = User(email="b@campus.edu", password_hash="x", display_name="Bea", is_verified=True)
    db_session.add(bidder)
    db_session.commit()
    place_bid(db_session, lid, bidder.id, 500)

    assert patch(client, seller_h, lid, handover_spot="Library").status_code == 200  # a place can change
    assert patch(client, seller_h, lid, starting_price=1).status_code == 409  # the price cannot


def test_a_too_long_spot_is_refused_on_edit(client, seller_h):
    lid = make(client, seller_h).json()["id"]
    assert patch(client, seller_h, lid, handover_spot="x" * 121).status_code == 422


def test_only_the_seller_can_change_it(client, seller_h):
    lid = make(client, seller_h, handover_spot="Main Canteen").json()["id"]
    other = auth_header(client, email="other@campus.edu", name="Olu")
    assert patch(client, other, lid, handover_spot="Somewhere else").status_code == 403
    assert client.get(f"/listings/{lid}").json()["handover_spot"] == "Main Canteen"


# --- where it shows up ------------------------------------------------------


def test_the_spot_is_public_on_the_detail_and_the_browse_card(client, seller_h):
    lid = make(client, seller_h, handover_spot="Main Canteen").json()["id"]
    assert client.get(f"/listings/{lid}").json()["handover_spot"] == "Main Canteen"  # no login needed
    card = client.get("/listings").json()["items"][0]
    assert card["handover_spot"] == "Main Canteen"


def test_the_spot_reveals_no_contact_details(client, seller_h):
    lid = make(client, seller_h, handover_spot="Main Canteen").json()["id"]
    assert "@" not in client.get(f"/listings/{lid}").text


def test_my_listings_and_my_bids_carry_the_spot(client, db_session, seller_h):
    lid = make(client, seller_h, handover_spot="Main Canteen").json()["id"]
    assert client.get("/me/listings", headers=seller_h).json()["items"][0]["handover_spot"] == "Main Canteen"
    bea = auth_header(client, email="bea@campus.edu", name="Bea")
    client.post(f"/listings/{lid}/bids", json={"amount": 500}, headers=bea)
    assert client.get("/me/bids", headers=bea).json()[0]["listing"]["handover_spot"] == "Main Canteen"


# --- the winner is told where to meet ---------------------------------------


def approve_flow(client, db_session, seller_h, **spot):
    lid = make(client, seller_h, **spot).json()["id"]
    bea = auth_header(client, email="bea@campus.edu", name="Bea")
    client.post(f"/listings/{lid}/bids", json={"amount": 500}, headers=bea)
    from app.models import Listing

    db_session.get(Listing, lid).closes_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    close_due_listings(db_session)
    r = client.post(f"/listings/{lid}/approve", headers=seller_h)
    assert r.status_code == 200
    return r.json(), db_session.scalars(select(Notification).where(Notification.type == "approved")).all()


def test_approval_tells_the_winner_where_to_meet(client, db_session, seller_h):
    detail, notes = approve_flow(client, db_session, seller_h, handover_spot="Main Canteen")
    assert len(notes) == 1 and "Meet at Main Canteen" in notes[0].body
    assert "Main Canteen" in detail["outcome_note"]  # the public note too


def test_approval_without_a_spot_asks_them_to_arrange_it(client, db_session, seller_h):
    detail, notes = approve_flow(client, db_session, seller_h)
    assert "Arrange the handover" in notes[0].body and "Meet at" not in notes[0].body
    assert detail["outcome_note"].endswith("awaiting handover")
