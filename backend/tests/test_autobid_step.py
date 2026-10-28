"""The buyer's own raise per automatic bid (the seller's minimum raise stays the default and the floor)."""

import random
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import AutoBid, Bid, Listing
from app.services.auction import BidError, min_valid_bid, place_bid, set_auto_bid
from tests.conftest import auth_header
from tests.test_autobid import NOW, history, listing, make_listing, people, seller, state  # noqa: F401  (shared fixtures)
from tests.test_autobid import lid as http_listing  # noqa: F401
from tests.test_autobid import put_max
from tests.test_listings import create


def autobid(db, listing, user, amount, step=None, at=0):
    return set_auto_bid(db, listing.id, user.id, amount, now=NOW + timedelta(seconds=at), step=step)


# The fixture listing: first bid 500, seller's minimum raise 50.


def test_without_a_chosen_step_nothing_changes(db_session, listing, people):
    autobid(db_session, listing, people["ann"], 1000)
    place_bid(db_session, listing.id, people["ben"].id, 600, now=NOW)
    assert history(db_session, listing.id)[-1] == ("ann", 650, True)  # 600 + the seller's 50


def test_a_chosen_step_raises_by_that_much_each_time(db_session, listing, people):
    autobid(db_session, listing, people["ann"], 1000, step=100)
    place_bid(db_session, listing.id, people["ben"].id, 600, now=NOW)
    assert history(db_session, listing.id)[-1] == ("ann", 700, True)  # 600 + her own 100, not 650
    place_bid(db_session, listing.id, people["ben"].id, 750, now=NOW)
    assert history(db_session, listing.id)[-1] == ("ann", 850, True)


def test_the_first_automatic_bid_still_opens_at_the_starting_price(db_session, listing, people):
    autobid(db_session, listing, people["ann"], 2000, step=300)
    assert history(db_session, listing.id) == [("ann", 500, True)]  # there is no price to raise yet


def test_a_big_step_never_goes_past_the_maximum(db_session, listing, people):
    autobid(db_session, listing, people["ann"], 650, step=500)
    place_bid(db_session, listing.id, people["ben"].id, 600, now=NOW)
    assert history(db_session, listing.id)[-1] == ("ann", 650, True)  # capped at her maximum, not 1,100


def test_a_challenger_with_a_big_step_jumps_over_the_leaders_maximum(db_session, listing, people):
    autobid(db_session, listing, people["ann"], 700)
    autobid(db_session, listing, people["ben"], 1000, step=150, at=1)
    assert state(db_session, listing) == ("ben", 850)  # one of ben's raises (150) over ann's 700


def test_the_leader_answers_with_their_own_step_when_the_challenger_runs_out(db_session, listing, people):
    autobid(db_session, listing, people["ann"], 1000, step=100)
    autobid(db_session, listing, people["ben"], 700, at=1)
    # ben goes up to his maximum (700) and ann answers with HER step: 800 (a default step would have given 750)
    assert state(db_session, listing) == ("ann", 800)
    assert [h[:2] for h in history(db_session, listing.id)][-2:] == [("ben", 700), ("ann", 800)]


def test_the_leaders_step_is_capped_by_their_maximum(db_session, listing, people):
    autobid(db_session, listing, people["ann"], 750, step=400)
    autobid(db_session, listing, people["ben"], 700, at=1)
    assert state(db_session, listing) == ("ann", 750)


def test_both_with_steps_still_settles_with_the_higher_maximum_ahead(db_session, listing, people):
    autobid(db_session, listing, people["ann"], 900, step=100)
    autobid(db_session, listing, people["ben"], 1200, step=200, at=1)
    leader, price = state(db_session, listing)
    assert leader == "ben" and 900 < price <= 1200
    bids = history(db_session, listing.id)
    assert all(b - a >= 50 for (_, a, _), (_, b, _) in zip(bids, bids[1:]))  # the seller's floor holds for every bid


# --- the seller's minimum is the floor ------------------------------------------------------------------


def test_a_step_below_the_sellers_minimum_is_refused_and_changes_nothing(db_session, listing, people):
    with pytest.raises(BidError) as e:
        autobid(db_session, listing, people["ann"], 1000, step=25)
    assert e.value.code == "invalid_step" and e.value.min_bid == 50
    assert history(db_session, listing.id) == [] and db_session.query(AutoBid).count() == 0


def test_a_step_equal_to_the_minimum_is_fine(db_session, listing, people):
    assert autobid(db_session, listing, people["ann"], 1000, step=50).step == 50


# --- changing it ------------------------------------------------------------------------------------------


def test_changing_only_the_step_keeps_the_place_in_the_queue(db_session, listing, people):
    first = autobid(db_session, listing, people["ann"], 1000, at=0)
    placed = first.set_at
    autobid(db_session, listing, people["ann"], 1000, step=200, at=60)
    db_session.expire_all()
    ann = db_session.query(AutoBid).one()
    assert ann.step == 200 and ann.set_at == placed  # a tie would still go to her; a changed MAXIMUM would reset it


def test_leaving_the_step_out_keeps_it_and_none_resets_it(db_session, listing, people):
    autobid(db_session, listing, people["ann"], 1000, step=200)
    set_auto_bid(db_session, listing.id, people["ann"].id, 1100, now=NOW + timedelta(seconds=5))  # only the maximum changes
    assert db_session.query(AutoBid).one().step == 200
    autobid(db_session, listing, people["ann"], 1100, step=None, at=10)
    assert db_session.query(AutoBid).one().step is None


# --- over HTTP --------------------------------------------------------------------------------------------


def put(client, headers, lid, **body):
    return client.put(f"/listings/{lid}/auto-bid", json=body, headers=headers)


def test_http_the_step_is_saved_returned_and_public(client, http_listing):
    a = auth_header(client, email="a@campus.edu", name="Ann")
    r = put(client, a, http_listing, max_amount=1000, step=100)
    assert r.status_code == 200 and r.json()["auto_bid"]["step"] == 100
    assert client.get("/me/auto-bids", headers=a).json() == [{"listing_id": http_listing, "max_amount": 1000, "step": 100}]
    public = client.get(f"/listings/{http_listing}/auto-bids").json()
    assert public[0]["step"] == 100 and "@" not in str(public)


def test_http_a_low_step_is_a_422_with_the_minimum(client, http_listing):
    a = auth_header(client, email="a@campus.edu", name="Ann")
    r = put(client, a, http_listing, max_amount=1000, step=10)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_step" and r.json()["detail"]["min_bid"] == 50
    assert put(client, a, http_listing, max_amount=1000, step=0).status_code == 422  # not a positive whole number


def test_http_omitting_the_step_keeps_it_and_null_resets_it(client, http_listing):
    a = auth_header(client, email="a@campus.edu", name="Ann")
    put(client, a, http_listing, max_amount=1000, step=150)
    assert put(client, a, http_listing, max_amount=1100).json()["auto_bid"]["step"] == 150
    assert put(client, a, http_listing, max_amount=1100, step=None).json()["auto_bid"]["step"] is None


def test_http_the_step_really_drives_the_bids(client, http_listing):
    a = auth_header(client, email="a@campus.edu", name="Ann")
    b = auth_header(client, email="b@campus.edu", name="Ben")
    put(client, a, http_listing, max_amount=1000, step=100)
    client.post(f"/listings/{http_listing}/bids", json={"amount": 600}, headers=b)
    amounts = [x["amount"] for x in client.get(f"/listings/{http_listing}/bids").json()]
    assert amounts[0] == 700  # newest first: Ann answered 600 + her 100


# --- the invariants still hold with random steps -----------------------------------------------------------


@pytest.mark.parametrize("seed", range(30))
def test_random_sequences_with_steps_stay_consistent(db_session, seller, people, seed):  # noqa: F811
    rng = random.Random(seed)
    lst = make_listing(db_session, seller, start=100, inc=10)
    users = list(people.values())
    for n in range(14):
        user = rng.choice(users)
        floor = min_valid_bid(db_session.get(Listing, lst.id))
        try:
            if rng.random() < 0.4:
                place_bid(db_session, lst.id, user.id, floor + rng.randrange(0, 60), now=NOW + timedelta(seconds=n))
            else:
                step = rng.choice([None, 10, 20, 35, 100])
                set_auto_bid(db_session, lst.id, user.id, floor + rng.randrange(0, 250), now=NOW + timedelta(seconds=n), step=step)
        except BidError:
            continue
        db_session.expire_all()
        fresh = db_session.get(Listing, lst.id)
        bids = db_session.scalars(select(Bid).where(Bid.listing_id == lst.id).order_by(Bid.id)).all()
        if not bids:
            continue
        assert bids[0].amount >= 100
        assert all(b.amount - a.amount >= 10 for a, b in zip(bids, bids[1:])), (seed, n)  # the seller's floor, always
        assert fresh.leading_bid_id == bids[-1].id and fresh.current_price == bids[-1].amount
        assert all(a.bidder_id != b.bidder_id for a, b in zip(bids, bids[1:])), (seed, n)
        assert bids[-1].bidder_id != seller.id
        needed = min_valid_bid(fresh)
        for auto in db_session.scalars(select(AutoBid).where(AutoBid.listing_id == lst.id)).all():
            assert auto.user_id == bids[-1].bidder_id or auto.max_amount < needed, (seed, n)
            # no automatic bid ever goes past its owner's maximum
        for bid in bids:
            if bid.is_auto:
                owner = db_session.scalar(select(AutoBid).where(AutoBid.listing_id == lst.id, AutoBid.user_id == bid.bidder_id))
                assert owner is not None
