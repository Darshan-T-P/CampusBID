"""Automatic bidding: the app bids for me, as little as needed, up to my (public) maximum."""

import random
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import AutoBid, Bid, Listing, ListingStatus, Notification
from app.services.auction import (
    BidError,
    min_valid_bid,
    place_bid,
    remove_auto_bid,
    set_auto_bid,
)
from tests.conftest import auth_header
from tests.test_auction import NOW, make_listing, make_user
from tests.test_listings import create


@pytest.fixture()
def seller(db_session):
    return make_user(db_session, "seller")


@pytest.fixture()
def people(db_session):
    return {name: make_user(db_session, name) for name in ("ann", "ben", "cat", "dan")}


@pytest.fixture()
def listing(db_session, seller):
    return make_listing(db_session, seller, start=500, inc=50)  # first bid 500, then +50


def history(db, listing_id):
    """[(bidder, amount, automatic?)] oldest first."""
    db.expire_all()
    rows = db.scalars(select(Bid).where(Bid.listing_id == listing_id).order_by(Bid.id)).all()
    return [(b.bidder.display_name, b.amount, b.is_auto) for b in rows]


def state(db, listing):
    db.refresh(listing)
    leader = db.get(Bid, listing.leading_bid_id).bidder.display_name if listing.leading_bid_id else None
    return leader, listing.current_price


def autobid(db, listing, user, amount, at=0):
    return set_auto_bid(db, listing.id, user.id, amount, now=NOW + timedelta(seconds=at))


# --- one maximum ------------------------------------------------------------


def test_a_lone_maximum_opens_at_the_starting_price_and_no_higher(db_session, listing, people):
    autobid(db_session, listing, people["ann"], 1800)
    assert history(db_session, listing.id) == [("ann", 500, True)]  # not 1800: only as much as needed
    assert state(db_session, listing) == ("ann", 500)


def test_a_manual_challenger_is_answered_one_step_above_not_at_the_maximum(db_session, listing, people):
    autobid(db_session, listing, people["ann"], 1000)
    place_bid(db_session, listing.id, people["ben"].id, 600, now=NOW)
    assert history(db_session, listing.id) == [("ann", 500, True), ("ben", 600, False), ("ann", 650, True)]
    assert state(db_session, listing) == ("ann", 650)


def test_a_manual_bid_beyond_the_maximum_wins(db_session, listing, people):
    autobid(db_session, listing, people["ann"], 1000)
    place_bid(db_session, listing.id, people["ben"].id, 1050, now=NOW)  # 1000 + one step: she can't answer
    assert state(db_session, listing) == ("ben", 1050)
    assert history(db_session, listing.id)[-1] == ("ben", 1050, False)


def test_a_manual_bid_exactly_at_the_maximum_still_wins_the_lead_back(db_session, listing, people):
    autobid(db_session, listing, people["ann"], 1000)
    place_bid(db_session, listing.id, people["ben"].id, 1000, now=NOW)  # she would need 1050
    assert state(db_session, listing) == ("ben", 1000)


# --- two or more maximums ---------------------------------------------------


def test_the_higher_maximum_wins_and_pays_one_step_over_the_other(db_session, listing, people):
    autobid(db_session, listing, people["ann"], 1000, at=0)
    autobid(db_session, listing, people["ben"], 800, at=1)
    assert state(db_session, listing) == ("ann", 850)
    assert history(db_session, listing.id) == [("ann", 500, True), ("ben", 800, True), ("ann", 850, True)]


def test_a_later_but_higher_maximum_takes_over_at_one_step_above(db_session, listing, people):
    autobid(db_session, listing, people["ann"], 800, at=0)
    autobid(db_session, listing, people["ben"], 1000, at=1)
    assert state(db_session, listing) == ("ben", 850)


def test_a_tie_goes_to_whoever_committed_first(db_session, listing, people):
    autobid(db_session, listing, people["ann"], 800, at=0)
    autobid(db_session, listing, people["ben"], 800, at=1)
    assert state(db_session, listing) == ("ann", 800)  # she pays her whole maximum, but keeps the lead


def test_matching_the_leaders_maximum_later_does_not_jump_the_queue(db_session, listing, people):
    autobid(db_session, listing, people["ann"], 800, at=0)
    autobid(db_session, listing, people["ben"], 900, at=1)  # ben leads at 850
    autobid(db_session, listing, people["ann"], 900, at=2)  # a NEW commitment: back of the line
    assert state(db_session, listing) == ("ben", 850)


def test_a_challenger_who_committed_earlier_wins_the_tie(db_session, listing, people):
    place_bid(db_session, listing.id, people["cat"].id, 500, now=NOW)  # a plain manual leader
    autobid(db_session, listing, people["ann"], 800, at=1)  # ann takes the lead at 550
    autobid(db_session, listing, people["ben"], 800, at=2)  # later tie: ann keeps it
    assert state(db_session, listing)[0] == "ann"


def test_three_maximums_settle_with_the_highest_one_step_over_the_runner_up(db_session, listing, people):
    autobid(db_session, listing, people["ann"], 1000, at=0)
    autobid(db_session, listing, people["cat"], 800, at=1)  # ann answers: 850
    autobid(db_session, listing, people["ben"], 900, at=2)  # beats cat's 800, but ann's 1000 still wins
    assert state(db_session, listing) == ("ann", 950)  # one step over the runner-up (ben, 900)
    assert db_session.query(AutoBid).count() == 3  # every maximum stays on record, public, even if idle


def test_a_maximum_that_cannot_beat_the_current_price_is_refused_outright(db_session, listing, people):
    autobid(db_session, listing, people["ann"], 1000, at=0)
    autobid(db_session, listing, people["ben"], 900, at=1)  # ann leads at 950; the next bid must be 1000
    with pytest.raises(BidError) as exc:
        autobid(db_session, listing, people["cat"], 800, at=2)
    assert exc.value.code == "too_low" and exc.value.min_bid == 1000


def test_every_automatic_bid_obeys_the_normal_increment_rule(db_session, listing, people):
    autobid(db_session, listing, people["ann"], 975, at=0)  # not on the 50-grid
    autobid(db_session, listing, people["ben"], 940, at=1)
    amounts = [a for _, a, _ in history(db_session, listing.id)]
    assert amounts[0] >= 500
    assert all(b - a >= 50 for a, b in zip(amounts, amounts[1:]))  # same rule as a human bid


def test_manual_bids_are_marked_manual_and_automatic_ones_automatic(db_session, listing, people):
    autobid(db_session, listing, people["ann"], 1000)
    place_bid(db_session, listing.id, people["ben"].id, 600, now=NOW)
    assert [auto for _, _, auto in history(db_session, listing.id)] == [True, False, True]


# --- changing and removing a maximum ----------------------------------------


def test_a_leader_can_raise_their_maximum_and_keeps_the_lead(db_session, listing, people):
    autobid(db_session, listing, people["ann"], 600, at=0)
    place_bid(db_session, listing.id, people["ben"].id, 600, now=NOW)  # ben 600 is above ann's 600? ties handled below
    leader, _ = state(db_session, listing)
    autobid(db_session, listing, people["ann"], 2000, at=2)  # raising it (as leader or challenger) works
    assert state(db_session, listing)[0] == "ann"


def test_maximums_below_what_is_needed_are_refused(db_session, listing, people):
    with pytest.raises(BidError) as exc:
        autobid(db_session, listing, people["ann"], 499)  # below the starting price
    assert exc.value.code == "too_low" and exc.value.min_bid == 500

    place_bid(db_session, listing.id, people["ben"].id, 500, now=NOW)
    with pytest.raises(BidError) as exc:
        autobid(db_session, listing, people["ann"], 549)  # needs 550 to beat ben
    assert exc.value.min_bid == 550

    with pytest.raises(BidError) as exc:
        autobid(db_session, listing, people["ben"], 499)  # a leader must at least cover their own price
    assert exc.value.min_bid == 500
    autobid(db_session, listing, people["ben"], 500)  # exactly their price is fine (a no-op ceiling)


def test_removing_a_maximum_stops_the_app_bidding_for_me(db_session, listing, people):
    autobid(db_session, listing, people["ann"], 1000)
    remove_auto_bid(db_session, listing.id, people["ann"].id, now=NOW)
    place_bid(db_session, listing.id, people["ben"].id, 600, now=NOW)
    assert state(db_session, listing) == ("ben", 600)  # no answer this time
    assert db_session.query(AutoBid).count() == 0
    with pytest.raises(BidError) as exc:
        remove_auto_bid(db_session, listing.id, people["ann"].id, now=NOW)
    assert exc.value.code == "not_found"


def test_bids_already_placed_stand_when_the_maximum_is_removed(db_session, listing, people):
    autobid(db_session, listing, people["ann"], 1000)
    remove_auto_bid(db_session, listing.id, people["ann"].id, now=NOW)
    assert state(db_session, listing) == ("ann", 500)


# --- who may set one --------------------------------------------------------


def test_the_seller_cannot_set_a_maximum_on_their_own_item(db_session, listing, seller):
    with pytest.raises(BidError) as exc:
        autobid(db_session, listing, seller, 1000)
    assert exc.value.code == "own_listing"


def test_no_maximum_on_a_closed_or_missing_auction(db_session, listing, people):
    with pytest.raises(BidError) as exc:
        set_auto_bid(db_session, listing.id, people["ann"].id, 1000, now=listing.closes_at)
    assert exc.value.code == "closed"
    with pytest.raises(BidError) as exc:
        set_auto_bid(db_session, 9999, people["ann"].id, 1000, now=NOW)
    assert exc.value.code == "not_found"
    assert db_session.query(AutoBid).count() == 0


def test_a_cancelled_listing_refuses_maximums(db_session, listing, people):
    listing.status = ListingStatus.cancelled
    db_session.commit()
    with pytest.raises(BidError) as exc:
        autobid(db_session, listing, people["ann"], 1000)
    assert exc.value.code == "closed"


def test_a_failed_attempt_leaves_nothing_behind(db_session, listing, people):
    with pytest.raises(BidError):
        autobid(db_session, listing, people["ann"], 10)
    assert db_session.query(AutoBid).count() == 0 and history(db_session, listing.id) == []


# --- notifications ----------------------------------------------------------


def test_the_person_outbid_by_an_automatic_bid_and_the_seller_are_told(db_session, listing, people, seller):
    autobid(db_session, listing, people["ann"], 1000)
    place_bid(db_session, listing.id, people["ben"].id, 600, now=NOW)  # ann answers at 650
    ben_notes = db_session.scalars(select(Notification).where(Notification.user_id == people["ben"].id)).all()
    assert [n.type for n in ben_notes] == ["outbid"] and "650" in ben_notes[0].body
    seller_bodies = [n.body for n in db_session.scalars(select(Notification).where(Notification.user_id == seller.id)).all()]
    assert any("(automatic bid)" in b for b in seller_bodies)


# --- the invariants hold under any sequence of operations -------------------


@pytest.mark.parametrize("seed", range(25))
def test_random_sequences_always_leave_a_consistent_auction(db_session, seller, people, seed):
    rng = random.Random(seed)
    lst = make_listing(db_session, seller, start=100, inc=10)
    users = list(people.values())

    for step in range(14):
        user = rng.choice(users)
        floor = min_valid_bid(db_session.get(Listing, lst.id))
        try:
            if rng.random() < 0.5:
                place_bid(db_session, lst.id, user.id, floor + rng.randrange(0, 60), now=NOW + timedelta(seconds=step))
            else:
                set_auto_bid(db_session, lst.id, user.id, floor + rng.randrange(0, 200), now=NOW + timedelta(seconds=step))
        except BidError:
            continue  # a refused action must simply change nothing

        db_session.expire_all()
        fresh = db_session.get(Listing, lst.id)
        bids = db_session.scalars(select(Bid).where(Bid.listing_id == lst.id).order_by(Bid.id)).all()
        if not bids:
            continue
        # 1. the same rules as a human bid: first >= start, every later one clears the increment
        assert bids[0].amount >= 100
        assert all(b.amount - a.amount >= 10 for a, b in zip(bids, bids[1:])), (seed, step)
        # 2. the listing points at the newest bid, which is the highest
        assert fresh.leading_bid_id == bids[-1].id and fresh.current_price == bids[-1].amount
        # 3. nobody outbids themselves
        assert all(a.bidder_id != b.bidder_id for a, b in zip(bids, bids[1:])), (seed, step)
        # 4. the seller never leads
        assert bids[-1].bidder_id != seller.id
        # 5. resolution is COMPLETE: nobody who could still validly beat the price is left waiting
        needed = min_valid_bid(fresh)
        for auto in db_session.scalars(select(AutoBid).where(AutoBid.listing_id == lst.id)).all():
            assert auto.user_id == bids[-1].bidder_id or auto.max_amount < needed, (seed, step, auto.max_amount, needed)


# --- over HTTP --------------------------------------------------------------


@pytest.fixture()
def lid(client):
    seller_h = auth_header(client, email="seller@campus.edu", name="Sam")
    return create(client, seller_h).json()["id"]  # starts at 500, +50


def put_max(client, headers, listing_id, amount):
    return client.put(f"/listings/{listing_id}/auto-bid", json={"max_amount": amount}, headers=headers)


def test_http_set_a_maximum_and_see_the_resulting_listing(client, lid):
    ann = auth_header(client, email="ann@campus.edu", name="Ann")
    r = put_max(client, ann, lid, 1800)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["auto_bid"]["bidder_name"] == "Ann" and body["auto_bid"]["max_amount"] == 1800
    assert body["listing"]["current_price"] == 500 and body["listing"]["leading_bidder"] == "Ann"  # opened at the start price


def test_http_maximums_are_public_and_names_only(client, lid):
    ann = auth_header(client, email="ann@campus.edu", name="Ann")
    ben = auth_header(client, email="ben@campus.edu", name="Ben")
    put_max(client, ann, lid, 1800)
    put_max(client, ben, lid, 900)
    r = client.get(f"/listings/{lid}/auto-bids")  # no login needed: nothing about bidding is private
    assert r.status_code == 200
    assert [(a["bidder_name"], a["max_amount"]) for a in r.json()] == [("Ann", 1800), ("Ben", 900)]  # highest first
    assert "@" not in r.text and set(r.json()[0]) == {"bidder_name", "max_amount", "set_at"}


def test_http_the_automatic_bids_show_in_the_public_history(client, lid):
    ann = auth_header(client, email="ann@campus.edu", name="Ann")
    ben = auth_header(client, email="ben@campus.edu", name="Ben")
    put_max(client, ann, lid, 1000)
    client.post(f"/listings/{lid}/bids", json={"amount": 600}, headers=ben)
    rows = client.get(f"/listings/{lid}/bids").json()
    assert [(b["bidder_name"], b["amount"], b["is_auto"]) for b in rows] == [("Ann", 650, True), ("Ben", 600, False), ("Ann", 500, True)]


def test_http_errors_use_the_same_codes_as_bidding(client, lid):
    ann = auth_header(client, email="ann@campus.edu", name="Ann")
    low = put_max(client, ann, lid, 100)
    assert low.status_code == 409 and low.json()["detail"] == {"code": "too_low", "message": "Your maximum must be at least 500", "min_bid": 500}
    assert put_max(client, ann, 9999, 600).status_code == 404
    assert client.put(f"/listings/{lid}/auto-bid", json={"max_amount": 600}).status_code == 401
    assert put_max(client, ann, lid, 0).status_code == 422
    assert put_max(client, ann, lid, 10_000_001).status_code == 422


def test_http_the_seller_gets_403(client):
    seller = auth_header(client, email="seller@campus.edu", name="Sam")
    lid = create(client, seller).json()["id"]
    r = put_max(client, seller, lid, 900)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "own_listing"


def test_http_remove_and_my_maximums(client, lid):
    ann = auth_header(client, email="ann@campus.edu", name="Ann")
    put_max(client, ann, lid, 1500)
    assert client.get("/me/auto-bids", headers=ann).json() == [{"listing_id": lid, "max_amount": 1500}]
    assert client.get("/me/auto-bids").status_code == 401

    assert client.delete(f"/listings/{lid}/auto-bid", headers=ann).status_code == 204
    assert client.get("/me/auto-bids", headers=ann).json() == []
    assert client.get(f"/listings/{lid}/auto-bids").json() == []
    assert client.delete(f"/listings/{lid}/auto-bid", headers=ann).status_code == 404  # nothing left to remove


def test_http_someone_elses_maximum_is_not_yours_to_remove(client, lid):
    ann = auth_header(client, email="ann@campus.edu", name="Ann")
    ben = auth_header(client, email="ben@campus.edu", name="Ben")
    put_max(client, ann, lid, 1500)
    assert client.delete(f"/listings/{lid}/auto-bid", headers=ben).status_code == 404  # Ben has none
    assert len(client.get(f"/listings/{lid}/auto-bids").json()) == 1  # Ann's is untouched
