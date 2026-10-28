"""Saved wants: "tell me when a cycle under ₹2,000 is listed"."""

import pytest

from app.models import Notification, Want
from app.services import wants
from tests.conftest import auth_header
from tests.test_listings import create


@pytest.fixture()
def sam(client):
    return auth_header(client, email="seller@campus.edu", name="Sam")


@pytest.fixture()
def alice(client):
    return auth_header(client, email="alice@campus.edu", name="Alice")


@pytest.fixture()
def bob(client):
    return auth_header(client, email="bob@campus.edu", name="Bob")


def want(client, headers, **body):
    return client.post("/me/wants", json=body, headers=headers)


def heard(client, headers):
    return [n for n in client.get("/notifications?limit=50", headers=headers).json()["items"] if n["type"] == "want_match"]


# --- managing alerts -------------------------------------------------------------------------------


def test_save_list_and_remove_an_alert(client, alice):
    r = want(client, alice, keywords="  cycle ", category="cycle", max_price=2000)
    assert r.status_code == 201 and r.json()["keywords"] == "cycle" and r.json()["category"] == "cycle" and r.json()["max_price"] == 2000
    assert [w["id"] for w in client.get("/me/wants", headers=alice).json()] == [r.json()["id"]]
    assert client.delete(f"/me/wants/{r.json()['id']}", headers=alice).status_code == 204
    assert client.get("/me/wants", headers=alice).json() == []


def test_an_alert_needs_something_to_look_for(client, alice):
    assert want(client, alice).status_code == 422
    assert want(client, alice, keywords="   ").status_code == 422
    assert want(client, alice, category="cycle").status_code == 201
    assert want(client, alice, max_price=500).status_code == 201


def test_bad_values_are_refused(client, alice):
    assert want(client, alice, keywords="x" * 81).status_code == 422
    assert want(client, alice, keywords="lamp", max_price=0).status_code == 422
    assert want(client, alice, keywords="lamp", max_price=10_000_001).status_code == 422
    assert want(client, alice, keywords="lamp", category="spaceship").status_code == 422


def test_the_same_alert_twice_is_refused(client, alice):
    assert want(client, alice, keywords="Cycle", category="cycle").status_code == 201
    assert want(client, alice, keywords="cycle", category="cycle").status_code == 409


def test_there_is_a_cap(client, alice, monkeypatch):
    monkeypatch.setattr(wants, "MAX_WANTS", 2)
    assert [want(client, alice, keywords=w).status_code for w in ("a1", "b2", "c3")] == [201, 201, 409]


def test_it_needs_login_and_alerts_are_private(client, alice, bob):
    assert client.get("/me/wants").status_code == 401
    wid = want(client, alice, keywords="lamp").json()["id"]
    assert client.get("/me/wants", headers=bob).json() == []
    assert client.delete(f"/me/wants/{wid}", headers=bob).status_code == 404  # looks exactly like a missing one
    assert len(client.get("/me/wants", headers=alice).json()) == 1


# --- matching -------------------------------------------------------------------------------------------


def test_a_matching_new_listing_notifies_the_student(client, sam, alice):
    want(client, alice, keywords="cycle", category="cycle", max_price=2000)
    lid = create(client, sam, title="Hero cycle", starting_price="1500").json()["id"]
    [note] = heard(client, alice)
    assert note["listing_id"] == lid and "Hero cycle" in note["title"]
    assert "1,500" in note["body"] and "cycle" in note["body"] and "2,000" in note["body"]


def test_every_part_of_the_alert_has_to_match(client, sam, alice):
    want(client, alice, keywords="hero cycle", category="cycle", max_price=2000)
    create(client, sam, title="Hero cycle", starting_price="2500")  # too expensive
    create(client, sam, title="Hero cycle", category="furniture", starting_price="500")  # wrong category
    create(client, sam, title="Mountain cycle", starting_price="500")  # "hero" missing
    assert heard(client, alice) == []
    create(client, sam, title="CYCLE by hero", starting_price="2000")  # any order, any case, price equal to the limit
    assert len(heard(client, alice)) == 1


def test_the_description_counts_too(client, sam, alice):
    want(client, alice, keywords="gears")
    create(client, sam, title="Bike", description="21 gears, barely used")
    assert len(heard(client, alice)) == 1


def test_a_category_only_or_price_only_alert_works(client, sam, alice, bob):
    want(client, alice, category="calculator")
    want(client, bob, max_price=300)
    create(client, sam, title="Casio", category="calculator", starting_price="900")
    assert len(heard(client, alice)) == 1 and heard(client, bob) == []
    create(client, sam, title="Lamp", category="other", starting_price="250")
    assert len(heard(client, bob)) == 1 and len(heard(client, alice)) == 1


def test_one_notification_per_student_however_many_alerts_match(client, sam, alice):
    want(client, alice, keywords="cycle")
    want(client, alice, category="cycle")
    create(client, sam, title="Hero cycle")
    assert len(heard(client, alice)) == 1


def test_the_seller_is_never_told_about_their_own_listing(client, sam):
    want(client, sam, keywords="cycle")
    create(client, sam, title="Hero cycle")
    assert heard(client, sam) == []


def test_everyone_with_a_matching_alert_hears_and_nobody_else(client, sam, alice, bob):
    want(client, alice, keywords="lamp")
    want(client, bob, keywords="calculator")
    create(client, sam, title="Desk lamp")
    assert len(heard(client, alice)) == 1 and heard(client, bob) == []


def test_the_notification_is_stored_for_someone_who_was_offline(client, db_session, sam, alice):
    want(client, alice, keywords="lamp")
    create(client, sam, title="Desk lamp")
    alice_id = db_session.query(Want).one().user_id
    stored = db_session.query(Notification).filter_by(user_id=alice_id, type="want_match", read_at=None).all()
    assert len(stored) == 1  # waiting, unread, whenever she next opens the app


def test_a_failed_listing_leaves_no_notification(client, sam, alice):
    want(client, alice, keywords="lamp")
    bad = create(client, sam, title="Desk lamp", files=[("images", ("a.png", b"not an image", "image/png"))])
    assert bad.status_code == 422 and heard(client, alice) == []


def test_deleted_alerts_stop_matching(client, sam, alice):
    wid = want(client, alice, keywords="lamp").json()["id"]
    client.delete(f"/me/wants/{wid}", headers=alice)
    create(client, sam, title="Desk lamp")
    assert heard(client, alice) == []


def test_deleting_an_account_removes_its_alerts(client, db_session, alice):
    want(client, alice, keywords="lamp")
    assert client.post("/me/delete", json={"password": "password123"}, headers=alice).status_code == 204
    assert db_session.query(Want).count() == 0
