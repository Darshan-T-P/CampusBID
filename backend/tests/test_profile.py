"""My profile: edit my details, change my password, and see a summary of what I sell and bid on."""

import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import settings
from app.core.ratelimit import limiter
from app.models import Listing, ListingStatus, User
from app.services.auction import close_due_listings, place_bid, set_auto_bid
from app.services import sale
from tests.conftest import auth_header, register
from tests.test_listings import create


def make_user(db, name, email=None):
    user = User(email=email or f"{name}@campus.edu", password_hash="x", display_name=name, is_verified=True)
    db.add(user)
    db.commit()
    return user


# --- editing my details -----------------------------------------------------


def test_change_my_name_department_and_year(client):
    h = auth_header(client)
    r = client.patch("/me", json={"display_name": "  Asha K ", "department": "Civil Engineering", "year_of_study": 3}, headers=h)
    assert r.status_code == 200
    assert (r.json()["display_name"], r.json()["department"], r.json()["year_of_study"]) == ("Asha K", "Civil Engineering", 3)
    assert client.get("/me", headers=h).json()["display_name"] == "Asha K"  # it stuck


def test_only_what_is_sent_changes_and_null_clears(client):
    h = auth_header(client)
    client.patch("/me", json={"department": "Civil", "year_of_study": 2}, headers=h)
    client.patch("/me", json={"display_name": "New name"}, headers=h)
    me = client.get("/me", headers=h).json()
    assert (me["display_name"], me["department"], me["year_of_study"]) == ("New name", "Civil", 2)
    cleared = client.patch("/me", json={"department": None, "year_of_study": None}, headers=h).json()
    assert cleared["department"] is None and cleared["year_of_study"] is None and cleared["display_name"] == "New name"


@pytest.mark.parametrize("bad", [{}, {"display_name": "   "}, {"display_name": "x" * 81}, {"year_of_study": 0}, {"year_of_study": 7}, {"department": "x" * 81}])
def test_bad_profile_changes_are_refused_and_change_nothing(client, bad):
    h = auth_header(client)
    assert client.patch("/me", json=bad, headers=h).status_code == 422
    assert client.get("/me", headers=h).json()["display_name"] == "Asha"


def test_a_new_name_shows_up_on_my_bids_and_listings(client):
    seller = auth_header(client, email="seller@campus.edu", name="Sam")
    lid = create(client, seller).json()["id"]
    bidder = auth_header(client, email="bea@campus.edu", name="Bea")
    client.post(f"/listings/{lid}/bids", json={"amount": 500}, headers=bidder)
    client.patch("/me", json={"display_name": "Beatrice"}, headers=bidder)
    assert client.get(f"/listings/{lid}/bids").json()[0]["bidder_name"] == "Beatrice"
    client.patch("/me", json={"display_name": "Samuel"}, headers=seller)
    assert client.get(f"/listings/{lid}").json()["seller"]["display_name"] == "Samuel"


def test_profile_changes_need_login_and_are_rate_limited(client):
    assert client.patch("/me", json={"display_name": "x"}).status_code == 401
    settings.rate_limit_enabled = True
    try:
        limiter.reset()
        h = auth_header(client)
        codes = [client.patch("/me", json={"display_name": f"Name {i}"}, headers=h).status_code for i in range(12)]
        assert codes[:10] == [200] * 10 and codes[10:] == [429, 429]
    finally:
        settings.rate_limit_enabled = False


# --- changing my password ---------------------------------------------------


def change(client, headers, current="password123", new="a-better-password"):
    return client.post("/me/password", json={"current_password": current, "new_password": new}, headers=headers)


def test_change_password_then_log_in_with_the_new_one(client):
    h = auth_header(client, password="password123")
    r = change(client, h)
    assert r.status_code == 200 and r.json()["access_token"]
    assert client.post("/auth/login", json={"email": "a@campus.edu", "password": "a-better-password"}).status_code == 200
    assert client.post("/auth/login", json={"email": "a@campus.edu", "password": "password123"}).status_code == 401  # old one is dead


def test_the_wrong_current_password_is_refused_and_nothing_changes(client):
    h = auth_header(client)
    r = change(client, h, current="not-my-password")
    assert r.status_code == 403
    assert client.post("/auth/login", json={"email": "a@campus.edu", "password": "password123"}).status_code == 200


def test_the_new_password_must_be_valid_and_different(client):
    h = auth_header(client)
    assert change(client, h, new="short").status_code == 422
    assert change(client, h, new="password123").status_code == 422  # same as the current one
    assert change(client, h, new="x" * 129).status_code == 422


def test_other_devices_are_signed_out_when_the_password_changes(client, db_session):
    first = register(client).json()["access_token"]
    # a token this person got "yesterday" (another phone, or a thief)
    old = jwt.encode({"sub": "1", "iat": int(time.time()) - 3600, "exp": int(time.time()) + 3600}, settings.secret_key, algorithm="HS256")
    h = {"Authorization": f"Bearer {first}"}
    old_h = {"Authorization": f"Bearer {old}"}
    assert client.get("/me", headers=old_h).status_code == 200  # works before

    fresh = change(client, h).json()["access_token"]
    assert client.get("/me", headers=old_h).status_code == 401  # signed out
    assert client.get("/me", headers={"Authorization": f"Bearer {fresh}"}).status_code == 200  # this device stays in


def test_changing_the_password_needs_login_and_is_rate_limited(client):
    assert client.post("/me/password", json={"current_password": "a", "new_password": "bbbbbbbb"}).status_code == 401
    settings.rate_limit_enabled = True
    try:
        limiter.reset()
        h = auth_header(client)
        codes = [change(client, h, current="wrong-password").status_code for _ in range(12)]
        assert codes[:10] == [403] * 10 and codes[10:] == [429, 429]  # guessing the current password is capped
    finally:
        settings.rate_limit_enabled = False


# --- the summary ------------------------------------------------------------


def test_a_new_account_has_an_all_zero_summary(client):
    h = auth_header(client)
    body = client.get("/me/summary", headers=h).json()
    assert all(v == 0 for v in body["selling"].values()) and all(v == 0 for v in body["buying"].values())
    assert body["unread_notifications"] == 0
    assert client.get("/me/summary").status_code == 401


def test_the_summary_counts_selling_and_buying_correctly(client, db_session):
    seller = auth_header(client, email="seller@campus.edu", name="Sam")
    seller_id = db_session.query(User).filter_by(email="seller@campus.edu").one().id
    bea = make_user(db_session, "bea")
    raj = make_user(db_session, "raj")

    open_one = create(client, seller).json()["id"]          # open, no bids
    open_two = create(client, seller).json()["id"]          # open; Bea leads, then Raj outbids her
    decide = create(client, seller).json()["id"]            # ends with Bea -> awaiting my decision
    sold = create(client, seller).json()["id"]              # Bea wins and buys at 700
    unsold = create(client, seller).json()["id"]            # ends with no bids
    cancelled = create(client, seller).json()["id"]

    place_bid(db_session, open_two, bea.id, 500)
    place_bid(db_session, open_two, raj.id, 550)
    place_bid(db_session, decide, bea.id, 500)
    place_bid(db_session, sold, bea.id, 700)
    set_auto_bid(db_session, open_one, bea.id, 900)         # Bea opens at the starting price on open_one

    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    for lid in (decide, sold, unsold):
        db_session.get(Listing, lid).closes_at = past
    db_session.commit()
    close_due_listings(db_session)
    sale.approve(db_session, sold, seller_id)
    sale.confirm_handover(db_session, sold, seller_id)
    client.post(f"/listings/{cancelled}/cancel", headers=seller)

    s = client.get("/me/summary", headers=seller).json()["selling"]
    assert s == {"total": 6, "open": 2, "awaiting_decision": 1, "awaiting_handover": 0, "sold": 1,
                 "unsold": 1, "other": 1, "earned": 700}

    from app.core.security import create_access_token
    bea_h = {"Authorization": f"Bearer {create_access_token(bea.id)}"}
    b = client.get("/me/summary", headers=bea_h).json()["buying"]
    # Bea bid on open_one (leads), open_two (outbid), decide (won, provisional), sold (bought)
    assert b == {"auctions": 4, "open": 2, "leading": 1, "outbid": 1, "won": 2, "spent": 700,
                 "bids_placed": 4, "automatic_maximums": 1}
    assert client.get("/me/summary", headers=bea_h).json()["unread_notifications"] > 0  # she was outbid, won, approved...


def test_the_summary_only_counts_my_own_activity(client, db_session):
    seller = auth_header(client, email="seller@campus.edu", name="Sam")
    create(client, seller)
    stranger = auth_header(client, email="stranger@campus.edu", name="Stu")
    s = client.get("/me/summary", headers=stranger).json()
    assert s["selling"]["total"] == 0 and s["buying"]["auctions"] == 0
