"""Deleting your own account: who may leave, what goes, what stays for other students."""

from datetime import timedelta

import pytest

from app.core.clock import utcnow
from app.models import AutoBid, Bid, Listing, ListingStatus, Notification, User, Watch
from app.services.auction import close_due_listings
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


def remove(client, headers, password="password123"):
    return client.post("/me/delete", json={"password": password}, headers=headers)


def bid(client, headers, listing_id, amount):
    return client.post(f"/listings/{listing_id}/bids", json={"amount": amount}, headers=headers)


def end(db, listing_id):
    listing = db.get(Listing, listing_id)
    listing.closes_at = utcnow() - timedelta(seconds=1)
    db.commit()
    close_due_listings(db)


def test_a_new_account_with_no_history_is_removed_and_the_email_is_free(client, db_session):
    h = auth_header(client, email="newbie@campus.edu", name="Nia")
    assert remove(client, h).status_code == 204
    assert db_session.query(User).count() == 0
    assert client.get("/me", headers=h).status_code == 401  # the old token is dead
    assert client.post("/auth/login", json={"email": "newbie@campus.edu", "password": "password123"}).status_code == 401
    assert auth_header(client, email="newbie@campus.edu", name="Nia Again")  # they can sign up again


def test_the_wrong_password_deletes_nothing(client, db_session, alice_h):
    r = remove(client, alice_h, password="not-my-password")
    assert r.status_code == 403 and db_session.query(User).count() == 1
    assert client.get("/me", headers=alice_h).status_code == 200


def test_it_needs_login_and_shares_the_guessing_limit(client, monkeypatch):
    from app.core.config import settings
    from app.core.ratelimit import limiter

    assert client.post("/me/delete", json={"password": "x"}).status_code == 401
    h = auth_header(client)
    limiter.reset()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    codes = [remove(client, h, password="wrong-password").status_code for _ in range(12)]
    assert codes[:10] == [403] * 10 and codes[10:] == [429, 429]


def test_their_own_leftovers_are_wiped(client, db_session, seller_h, alice_h, bob_h):
    lid = create(client, seller_h).json()["id"]
    client.put(f"/listings/{lid}/watch", headers=alice_h)
    client.put(f"/listings/{lid}/auto-bid", json={"max_amount": 600}, headers=alice_h)
    client.put(f"/listings/{lid}/auto-bid", json={"max_amount": 900}, headers=bob_h)  # Bob now leads; Alice is outbid
    assert db_session.query(Notification).filter_by(user_id=2).count() >= 1
    assert db_session.query(AutoBid).filter_by(user_id=2).count() == 1
    assert remove(client, alice_h).status_code == 204
    assert db_session.query(Notification).filter_by(user_id=2).count() == 0
    assert db_session.query(Watch).count() == 0 and db_session.query(AutoBid).filter_by(user_id=2).count() == 0
    assert db_session.query(AutoBid).filter_by(user_id=3).count() == 1  # nobody else's data is touched


# --- who may not leave yet -----------------------------------------------------


def test_an_open_auction_blocks_a_seller(client, db_session, seller_h):
    create(client, seller_h)
    r = remove(client, seller_h)
    assert r.status_code == 409 and "1 open auction" in r.json()["detail"]
    assert db_session.query(User).count() == 1


def test_cancelling_frees_them(client, db_session, seller_h):
    lid = create(client, seller_h).json()["id"]
    client.post(f"/listings/{lid}/cancel", headers=seller_h)
    assert remove(client, seller_h).status_code == 204


def test_leading_an_open_auction_blocks_a_bidder_but_being_outbid_does_not(client, seller_h, alice_h, bob_h):
    lid = create(client, seller_h).json()["id"]
    bid(client, alice_h, lid, 500)
    r = remove(client, alice_h)
    assert r.status_code == 409 and "leading 1 open auction" in r.json()["detail"]
    bid(client, bob_h, lid, 550)
    assert remove(client, alice_h).status_code == 204  # outbid: nobody depends on Alice now


def test_a_sale_in_progress_blocks_both_sides(client, db_session, seller_h, alice_h):
    lid = create(client, seller_h).json()["id"]
    bid(client, alice_h, lid, 500)
    end(db_session, lid)  # pending approval
    assert "still waiting" in remove(client, seller_h).json()["detail"]
    assert "still being settled" in remove(client, alice_h).json()["detail"]


def test_an_auction_that_already_ran_out_of_time_does_not_block(client, db_session, seller_h):
    lid = create(client, seller_h).json()["id"]
    listing = db_session.get(Listing, lid)
    listing.closes_at = utcnow() - timedelta(minutes=1)  # over, but the closer hasn't run yet
    db_session.commit()
    assert remove(client, seller_h).status_code == 204  # it closed unsold, so no one is waiting


# --- what stays for others ------------------------------------------------------


def test_someone_with_history_is_anonymised_not_erased(client, db_session, seller_h, alice_h, bob_h):
    lid = create(client, seller_h).json()["id"]
    bid(client, alice_h, lid, 500)
    bid(client, bob_h, lid, 550)  # Alice is outbid, free to leave
    assert remove(client, alice_h).status_code == 204
    alice = db_session.get(User, 2)
    assert alice.display_name == "Deleted user" and alice.email.endswith("@deleted.invalid") and alice.password_hash == "!deleted"
    assert alice.department is None and alice.year_of_study is None and alice.is_verified is False
    history = client.get(f"/listings/{lid}/bids").json()
    assert [b["bidder_name"] for b in history] == ["Bob", "Deleted user"]  # the auction's record stays intact
    assert db_session.query(Bid).count() == 2
    assert client.get("/me", headers=alice_h).status_code == 401
    assert client.post("/auth/login", json={"email": "alice@campus.edu", "password": "password123"}).status_code == 401
    assert auth_header(client, email="alice@campus.edu", name="Alice")  # the real address can register again


def test_a_deleted_sellers_finished_listings_show_deleted_user(client, db_session, seller_h):
    lid = create(client, seller_h).json()["id"]
    client.post(f"/listings/{lid}/cancel", headers=seller_h)
    remove(client, seller_h)
    assert client.get(f"/listings/{lid}").json()["seller"]["display_name"] == "Deleted user"
    assert db_session.get(Listing, lid).status == ListingStatus.cancelled
