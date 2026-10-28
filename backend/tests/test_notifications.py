"""Notifications (plan A5): who is told what, exactly once, and who can read them."""

import threading
import time
from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.models import Listing, Notification, User
from app.services import notifications
from app.services.auction import begin_write, close_due_listings, close_if_due, ensure_closed
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
    return create(client, seller_h).json()["id"]  # starts at 500, increment 50


def bid(client, headers, listing_id, amount):
    r = client.post(f"/listings/{listing_id}/bids", json={"amount": amount}, headers=headers)
    return r


def feed(client, headers, **params):
    r = client.get("/notifications", headers=headers, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def types(client, headers, **params):
    return [n["type"] for n in feed(client, headers, **params)["items"]]


def expire(db, listing_id):
    listing = db.get(Listing, listing_id)
    listing.closes_at = utcnow() - timedelta(seconds=1)
    db.commit()


def post(client, headers, listing_id, action, **kwargs):
    return client.post(f"/listings/{listing_id}/{action}", headers=headers, **kwargs)


# --- bids -------------------------------------------------------------------


def test_bids_notify_the_seller_and_the_person_outbid(client, lid, seller_h, alice_h, bob_h):
    bid(client, alice_h, lid, 500)
    assert types(client, seller_h) == ["new_bid"]
    assert types(client, alice_h) == []  # first bid: nobody to outbid, and you aren't told about yourself

    bid(client, bob_h, lid, 550)
    alice = feed(client, alice_h)["items"]
    assert [n["type"] for n in alice] == ["outbid"]
    assert "Hero cycle" in alice[0]["title"] and "550" in alice[0]["body"]
    assert alice[0]["listing_id"] == lid
    assert types(client, bob_h) == []  # the new leader gets nothing
    assert types(client, seller_h) == ["new_bid", "new_bid"]
    assert "Bob" in feed(client, seller_h)["items"][0]["body"] and "550" in feed(client, seller_h)["items"][0]["body"]


def test_a_refused_bid_creates_no_notifications(client, db_session, lid, alice_h, bob_h):
    bid(client, alice_h, lid, 500)
    before = db_session.query(Notification).count()
    assert bid(client, bob_h, lid, 520).status_code == 409  # too low
    assert db_session.query(Notification).count() == before


def test_notify_never_tells_the_person_who_caused_the_event(db_session):
    user = User(email="x@campus.edu", password_hash="x", display_name="X", is_verified=True)
    db_session.add(user)
    db_session.commit()
    assert notifications.notify(db_session, user.id, "t", "title", actor_id=user.id) is None
    db_session.commit()
    assert db_session.query(Notification).count() == 0


# --- closing ----------------------------------------------------------------


def test_close_with_bids_tells_winner_and_seller_only(client, db_session, lid, seller_h, alice_h, bob_h):
    bid(client, alice_h, lid, 500)
    bid(client, bob_h, lid, 550)
    expire(db_session, lid)
    close_due_listings(db_session)

    assert "won" in types(client, bob_h)
    won = [n for n in feed(client, bob_h)["items"] if n["type"] == "won"][0]
    assert "550" in won["body"] and "provisional" in won["body"]
    assert "auction_ended" in types(client, seller_h)
    assert "won" not in types(client, alice_h)  # the loser is not told they won
    assert types(client, alice_h) == ["outbid"]  # nothing new beyond the earlier outbid


def test_unsold_tells_the_seller(client, db_session, lid, seller_h, alice_h):
    expire(db_session, lid)
    close_due_listings(db_session)
    assert types(client, seller_h) == ["unsold"]
    assert types(client, alice_h) == []


def test_closing_announces_exactly_once_however_it_is_triggered(client, db_session, lid, seller_h, alice_h):
    bid(client, alice_h, lid, 500)
    expire(db_session, lid)
    close_due_listings(db_session)  # the background sweep
    close_due_listings(db_session)  # again
    client.get(f"/listings/{lid}")  # a viewer's lazy close
    assert types(client, alice_h) == ["won"]
    assert types(client, seller_h).count("auction_ended") == 1


def test_viewing_an_expired_listing_closes_it_and_notifies(client, db_session, lid, seller_h):
    expire(db_session, lid)
    assert client.get(f"/listings/{lid}").json()["status"] == "unsold"  # nobody swept it
    assert types(client, seller_h) == ["unsold"]


def test_a_late_bid_attempt_closes_the_listing_and_notifies_once(client, db_session, lid, seller_h, alice_h, bob_h):
    bid(client, alice_h, lid, 500)
    expire(db_session, lid)
    assert bid(client, bob_h, lid, 9999).status_code == 409  # late: refused, and it closes the auction
    assert types(client, alice_h) == ["won"]
    assert types(client, bob_h) == []


def test_lazy_close_waits_for_a_concurrent_closer_and_does_not_announce_twice(client, db_session, lid, seller_h):
    """Deterministic: a reader and another closer overlap. Only one may announce the close.

    Without the write lock + re-check, the waiting reader would close it again and the
    seller would get two 'unsold' notifications.
    """
    expire(db_session, lid)
    engine = db_session.get_bind()
    stale_view = db_session.get(Listing, lid)  # what a request thread loaded: still "active"
    db_session.expunge(stale_view)

    def reader():
        with Session(engine) as s:
            ensure_closed(s, s.get(Listing, lid))

    with Session(engine) as closer:
        begin_write(closer)  # the other closer holds the lock...
        thread = threading.Thread(target=reader)
        thread.start()
        time.sleep(0.3)
        assert thread.is_alive(), "reader should wait behind the closer"
        fresh = closer.get(Listing, lid)
        assert close_if_due(closer, fresh, utcnow())
        closer.commit()  # ...and announces + releases here
    thread.join(timeout=10)

    assert types(client, seller_h) == ["unsold"]


def test_many_simultaneous_viewers_still_announce_once(client, db_session, lid, seller_h):
    expire(db_session, lid)
    barrier = threading.Barrier(6)

    def view():
        barrier.wait()
        client.get(f"/listings/{lid}")

    threads = [threading.Thread(target=view) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert types(client, seller_h) == ["unsold"]


# --- cancel and sale steps --------------------------------------------------


def test_cancel_tells_every_bidder_once_and_not_the_seller(client, lid, seller_h, alice_h, bob_h):
    bid(client, alice_h, lid, 500)
    bid(client, bob_h, lid, 550)
    bid(client, alice_h, lid, 600)  # Alice bid twice: still only one cancellation notice
    assert post(client, seller_h, lid, "cancel").status_code == 200

    assert types(client, alice_h).count("cancelled") == 1
    assert types(client, bob_h).count("cancelled") == 1
    assert "cancelled" not in types(client, seller_h)  # the seller did it themselves


def test_sale_decisions_tell_the_winner_not_the_seller(client, db_session, lid, seller_h, alice_h):
    bid(client, alice_h, lid, 500)
    expire(db_session, lid)
    close_due_listings(db_session)
    seller_before = len(feed(client, seller_h)["items"])

    post(client, seller_h, lid, "approve")
    approved = feed(client, alice_h)["items"][0]
    assert approved["type"] == "approved" and "500" in approved["body"]
    post(client, seller_h, lid, "handover")
    assert feed(client, alice_h)["items"][0]["type"] == "completed"
    assert len(feed(client, seller_h)["items"]) == seller_before  # seller acted; not told about own actions


def test_rejection_and_failed_pickup_messages(client, db_session, seller_h, alice_h):
    a = create(client, seller_h).json()["id"]
    b = create(client, seller_h).json()["id"]
    for listing_id in (a, b):
        bid(client, alice_h, listing_id, 500)
        expire(db_session, listing_id)
    close_due_listings(db_session)

    post(client, seller_h, a, "reject", json={"reason": "Not a campus student"})
    rejected = [n for n in feed(client, alice_h)["items"] if n["type"] == "rejected"][0]
    assert "Not a campus student" in rejected["body"]

    post(client, seller_h, b, "approve")
    post(client, seller_h, b, "pickup-failed")
    assert feed(client, alice_h)["items"][0]["type"] == "pickup_failed"


# --- the API ----------------------------------------------------------------


def test_requires_login(client):
    assert client.get("/notifications").status_code == 401
    assert client.post("/notifications/1/read").status_code == 401
    assert client.post("/notifications/read-all").status_code == 401


def test_you_only_ever_see_your_own(client, lid, seller_h, alice_h, bob_h):
    bid(client, alice_h, lid, 500)
    bid(client, bob_h, lid, 550)
    assert len(feed(client, alice_h)["items"]) == 1 and len(feed(client, bob_h)["items"]) == 0
    assert "@" not in client.get("/notifications", headers=seller_h).text  # no emails anywhere


def test_default_is_newest_first_and_since_id_is_an_oldest_first_cursor(client, lid, seller_h, alice_h, bob_h):
    bid(client, alice_h, lid, 500)
    bid(client, bob_h, lid, 550)
    bid(client, alice_h, lid, 600)
    ids = [n["id"] for n in feed(client, seller_h)["items"]]
    assert ids == sorted(ids, reverse=True) and len(ids) == 3  # history: newest first

    after_first = feed(client, seller_h, since_id=ids[-1])
    assert [n["id"] for n in after_first["items"]] == sorted(ids)[1:]  # cursor: oldest first, excludes the cursor
    assert after_first["latest_id"] == ids[0]


def test_polling_returns_only_what_is_new(client, lid, seller_h, alice_h, bob_h):
    bid(client, alice_h, lid, 500)
    cursor = feed(client, seller_h)["latest_id"]
    assert feed(client, seller_h, since_id=cursor)["items"] == []  # nothing new
    assert feed(client, seller_h, since_id=cursor)["latest_id"] is None

    bid(client, bob_h, lid, 550)
    new = feed(client, seller_h, since_id=cursor)
    assert len(new["items"]) == 1 and "550" in new["items"][0]["body"]
    # Advancing the cursor means the same notification is never delivered twice.
    assert feed(client, seller_h, since_id=new["latest_id"])["items"] == []


def test_unread_count_is_total_not_just_this_page(client, lid, seller_h, alice_h, bob_h):
    bid(client, alice_h, lid, 500)
    bid(client, bob_h, lid, 550)
    bid(client, alice_h, lid, 600)
    page = feed(client, seller_h, limit=1)
    assert len(page["items"]) == 1 and page["unread_count"] == 3
    assert client.get("/notifications", headers=seller_h, params={"limit": 0}).status_code == 422
    assert client.get("/notifications", headers=seller_h, params={"limit": 101}).status_code == 422


def test_mark_one_read(client, lid, seller_h, alice_h, bob_h):
    bid(client, alice_h, lid, 500)
    bid(client, bob_h, lid, 550)
    first = feed(client, seller_h)["items"][-1]
    assert client.post(f"/notifications/{first['id']}/read", headers=seller_h).status_code == 204

    page = feed(client, seller_h)
    assert page["unread_count"] == 1
    stamped = [n for n in page["items"] if n["id"] == first["id"]][0]["read_at"]
    assert stamped is not None
    assert [n["id"] for n in feed(client, seller_h, unread_only="true")["items"]] != [first["id"]]

    assert client.post(f"/notifications/{first['id']}/read", headers=seller_h).status_code == 204  # idempotent
    again = [n for n in feed(client, seller_h)["items"] if n["id"] == first["id"]][0]["read_at"]
    assert again == stamped  # the original read time is kept


def test_cannot_mark_someone_elses_notification(client, lid, seller_h, alice_h):
    bid(client, alice_h, lid, 500)
    seller_note = feed(client, seller_h)["items"][0]["id"]
    assert client.post(f"/notifications/{seller_note}/read", headers=alice_h).status_code == 404
    assert client.post("/notifications/9999/read", headers=alice_h).status_code == 404
    assert feed(client, seller_h)["unread_count"] == 1  # untouched


def test_read_all(client, lid, seller_h, alice_h, bob_h):
    bid(client, alice_h, lid, 500)
    bid(client, bob_h, lid, 550)
    assert client.post("/notifications/read-all", headers=seller_h).json() == {"marked": 2}
    assert feed(client, seller_h)["unread_count"] == 0
    assert client.post("/notifications/read-all", headers=seller_h).json() == {"marked": 0}
    assert feed(client, alice_h)["unread_count"] == 1  # other people's are untouched
