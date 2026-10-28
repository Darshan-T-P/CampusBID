"""The minimum raise is worked out by the app from the starting price; sellers no longer type one."""

import pytest

from app.models import Listing
from app.services.listings import default_min_increment
from tests.conftest import auth_header
from tests.test_listings import create


@pytest.fixture()
def sam(client):
    return auth_header(client, email="seller@campus.edu", name="Sam")


@pytest.mark.parametrize(
    "price,step",
    [(1, 1), (10, 1), (50, 2), (100, 5), (150, 5), (200, 10), (500, 25), (800, 50), (1800, 100), (4002, 200), (25000, 1000)],
)
def test_the_step_is_about_five_percent_rounded_to_a_tidy_number(price, step):
    assert default_min_increment(price) == step


def test_it_never_goes_below_one_or_above_the_price_cap():
    assert default_min_increment(1) >= 1
    assert default_min_increment(10_000_000) <= 10_000_000


def test_it_grows_with_the_price():
    steps = [default_min_increment(p) for p in (100, 500, 2000, 10000, 100000)]
    assert steps == sorted(steps) and len(set(steps)) == len(steps)


def test_leaving_the_field_out_uses_the_automatic_step(client, sam):
    r = create(client, sam, starting_price="1800", min_increment=None)
    assert r.status_code == 201 and r.json()["min_increment"] == 100
    assert r.json()["min_next_bid"] == 1800  # the first bid is just the starting price


def test_the_first_raise_after_a_bid_uses_it(client, sam):
    buyer = auth_header(client, email="b@campus.edu", name="Bea")
    lid = create(client, sam, starting_price="500", min_increment=None).json()["id"]
    client.post(f"/listings/{lid}/bids", json={"amount": 500}, headers=buyer)
    assert client.get(f"/listings/{lid}").json()["min_next_bid"] == 525  # 500 + the automatic 25


def test_an_explicit_value_is_still_honoured_for_other_callers(client, sam):
    assert create(client, sam, starting_price="1800", min_increment="75").json()["min_increment"] == 75


def test_a_nonsense_value_is_still_refused(client, sam):
    assert create(client, sam, min_increment="0").status_code == 422


def test_changing_the_starting_price_moves_the_raise_with_it(client, sam):
    lid = create(client, sam, starting_price="500", min_increment=None).json()["id"]
    r = client.patch(f"/listings/{lid}", json={"starting_price": 2000}, headers=sam)
    assert r.status_code == 200 and r.json()["min_increment"] == 100


def test_an_explicit_raise_in_an_edit_is_kept(client, sam):
    lid = create(client, sam, starting_price="500", min_increment=None).json()["id"]
    r = client.patch(f"/listings/{lid}", json={"starting_price": 2000, "min_increment": 40}, headers=sam)
    assert r.json()["min_increment"] == 40


def test_editing_other_fields_leaves_the_raise_alone(client, sam):
    lid = create(client, sam, starting_price="500", min_increment=None).json()["id"]
    r = client.patch(f"/listings/{lid}", json={"description": "Now with a bell"}, headers=sam)
    assert r.json()["min_increment"] == 25


def test_after_a_bid_neither_the_price_nor_the_raise_can_change(client, sam):
    buyer = auth_header(client, email="b@campus.edu", name="Bea")
    lid = create(client, sam, starting_price="500", min_increment=None).json()["id"]
    client.post(f"/listings/{lid}/bids", json={"amount": 500}, headers=buyer)
    assert client.patch(f"/listings/{lid}", json={"starting_price": 9000}, headers=sam).status_code == 409
    assert client.get(f"/listings/{lid}").json()["min_increment"] == 25


def test_old_listings_keep_whatever_raise_their_seller_chose(client, db_session, sam):
    lid = create(client, sam, starting_price="500", min_increment="60").json()["id"]
    assert db_session.get(Listing, lid).min_increment == 60  # nothing rewrites existing auctions
