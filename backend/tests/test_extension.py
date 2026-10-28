"""Last-minute extensions: a valid bid in the last 30 s moves the closing time to 60 s after that bid."""

from datetime import timedelta

import pytest

from app.models import Listing, ListingStatus
from app.services.auction import BidError, close_due_listings, place_bid, set_auto_bid
from tests.conftest import auth_header
from tests.test_auction import NOW, make_listing, make_user
from tests.test_listings import create


@pytest.fixture()
def seller(db_session):
    return make_user(db_session, "seller")


@pytest.fixture()
def ann(db_session):
    return make_user(db_session, "ann")


@pytest.fixture()
def ben(db_session):
    return make_user(db_session, "ben")


@pytest.fixture()
def listing(db_session, seller):
    return make_listing(db_session, seller, start=100, inc=10)  # closes NOW + 1 h


def seconds_before_close(listing, seconds):
    return listing.closes_at - timedelta(seconds=seconds)


def reload(db, listing):
    db.refresh(listing)
    return listing


# --- the boundary -----------------------------------------------------------


def test_a_bid_with_more_than_30_seconds_left_does_not_extend(db_session, listing, ann):
    original = listing.closes_at
    place_bid(db_session, listing.id, ann.id, 100, now=seconds_before_close(listing, 31))
    assert reload(db_session, listing).closes_at == original and listing.extension_count == 0


def test_a_bid_with_exactly_30_seconds_left_extends(db_session, listing, ann):
    bid_time = seconds_before_close(listing, 30)
    place_bid(db_session, listing.id, ann.id, 100, now=bid_time)
    assert reload(db_session, listing).closes_at == bid_time + timedelta(seconds=60)
    assert listing.extension_count == 1


def test_a_bid_in_the_last_second_extends_to_60_seconds_after_that_bid(db_session, listing, ann):
    bid_time = seconds_before_close(listing, 1)
    place_bid(db_session, listing.id, ann.id, 100, now=bid_time)
    assert reload(db_session, listing).closes_at == bid_time + timedelta(seconds=60)  # not +60 from the old end


def test_the_extension_always_adds_time(db_session, listing, ann):
    original = listing.closes_at
    place_bid(db_session, listing.id, ann.id, 100, now=seconds_before_close(listing, 29))
    assert reload(db_session, listing).closes_at > original


def test_a_bid_at_or_after_the_closing_time_is_refused_and_extends_nothing(db_session, listing, ann):
    original = listing.closes_at
    with pytest.raises(BidError) as exc:
        place_bid(db_session, listing.id, ann.id, 100, now=original)
    assert exc.value.code == "closed"
    # it was too late: the listing closed instead of being extended
    assert reload(db_session, listing).status == ListingStatus.unsold and listing.closes_at == original


def test_a_refused_bid_in_the_last_seconds_does_not_extend(db_session, listing, ann, ben):
    place_bid(db_session, listing.id, ann.id, 100, now=seconds_before_close(listing, 90))
    original = reload(db_session, listing).closes_at
    with pytest.raises(BidError):  # too low, even though it arrives in the final seconds
        place_bid(db_session, listing.id, ben.id, 105, now=seconds_before_close(listing, 10))
    assert reload(db_session, listing).closes_at == original and listing.extension_count == 0


# --- repeated extensions ----------------------------------------------------


def test_each_late_bid_extends_again_and_is_counted(db_session, listing, ann, ben):
    first = seconds_before_close(listing, 20)
    place_bid(db_session, listing.id, ann.id, 100, now=first)
    close_1 = reload(db_session, listing).closes_at
    assert close_1 == first + timedelta(seconds=60)

    second = close_1 - timedelta(seconds=15)  # late again, in the NEW closing window
    place_bid(db_session, listing.id, ben.id, 110, now=second)
    assert reload(db_session, listing).closes_at == second + timedelta(seconds=60)
    assert listing.extension_count == 2


def test_an_early_bid_after_an_extension_changes_nothing(db_session, listing, ann, ben):
    place_bid(db_session, listing.id, ann.id, 100, now=seconds_before_close(listing, 20))
    extended = reload(db_session, listing).closes_at
    place_bid(db_session, listing.id, ben.id, 110, now=extended - timedelta(seconds=45))  # outside the window
    assert reload(db_session, listing).closes_at == extended and listing.extension_count == 1


# --- automatic bids ---------------------------------------------------------


def test_a_manual_late_bid_and_the_automatic_answer_it_triggers_extend_once_not_twice(db_session, listing, ann, ben):
    set_auto_bid(db_session, listing.id, ann.id, 500, now=NOW)  # ann leads at 100, ready to answer up to 500
    bid_time = seconds_before_close(listing, 10)
    place_bid(db_session, listing.id, ben.id, 120, now=bid_time)  # ann's maximum answers at the same instant
    assert reload(db_session, listing).closes_at == bid_time + timedelta(seconds=60)  # +60 once, not stacked
    assert listing.extension_count == 1
    assert db_session.get(Listing, listing.id).leading_bid_id is not None


def test_a_standing_maximum_extends_when_its_automatic_bid_lands_late(db_session, listing, ann):
    bid_time = seconds_before_close(listing, 12)
    set_auto_bid(db_session, listing.id, ann.id, 300, now=bid_time)  # opens at the starting price: a bid in the last 30 s
    assert reload(db_session, listing).closes_at == bid_time + timedelta(seconds=60)


def test_setting_a_maximum_early_does_not_extend(db_session, listing, ann):
    original = listing.closes_at
    set_auto_bid(db_session, listing.id, ann.id, 300, now=seconds_before_close(listing, 600))
    assert reload(db_session, listing).closes_at == original


# --- closing respects the new time ------------------------------------------


def test_the_closer_leaves_an_extended_auction_open_until_the_new_time(db_session, listing, ann):
    original = listing.closes_at
    place_bid(db_session, listing.id, ann.id, 100, now=seconds_before_close(listing, 5))
    new_close = reload(db_session, listing).closes_at

    assert close_due_listings(db_session, now=original + timedelta(seconds=1)) == []  # past the OLD time: still open
    assert reload(db_session, listing).status == ListingStatus.active
    assert [l.id for l in close_due_listings(db_session, now=new_close)] == [listing.id]  # closes at the new one
    assert reload(db_session, listing).status == ListingStatus.pending_approval


def test_a_bid_after_the_original_end_but_inside_the_extension_is_accepted(db_session, listing, ann, ben):
    original = listing.closes_at
    place_bid(db_session, listing.id, ann.id, 100, now=seconds_before_close(listing, 5))
    place_bid(db_session, listing.id, ben.id, 110, now=original + timedelta(seconds=20))  # past the old end, before the new one
    assert reload(db_session, listing).current_price == 110


# --- over HTTP --------------------------------------------------------------


def test_http_a_late_bid_moves_the_closing_time_everyone_sees(client, db_session):
    from app.core.clock import utcnow

    seller_h = auth_header(client, email="seller@campus.edu", name="Sam")
    bidder_h = auth_header(client, email="bidder@campus.edu", name="Bea")
    lid = create(client, seller_h).json()["id"]
    before = client.get(f"/listings/{lid}").json()
    assert before["extension_count"] == 0

    listing = db_session.get(Listing, lid)
    listing.closes_at = utcnow() + timedelta(seconds=20)  # 20 s left: inside the window
    db_session.commit()

    r = client.post(f"/listings/{lid}/bids", json={"amount": 500}, headers=bidder_h)
    assert r.status_code == 201
    after = client.get(f"/listings/{lid}").json()  # anyone, no login
    assert after["extension_count"] == 1
    from datetime import datetime
    closes = datetime.fromisoformat(after["closes_at"].replace("Z", "+00:00"))
    assert 55 <= (closes - utcnow()).total_seconds() <= 61
    assert r.json()["listing"]["extension_count"] == 1  # the bidder's own response already shows it
