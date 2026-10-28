"""Saved auctions, closing reminders, and results for everyone who followed an auction."""

from datetime import timedelta

import pytest

from app.core.clock import utcnow
from app.models import ClosingReminder, Listing, Notification, Watch
from app.services import watchlist
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


@pytest.fixture()
def cara_h(client):
    return auth_header(client, email="cara@campus.edu", name="Cara")


@pytest.fixture()
def lid(client, seller_h):
    return create(client, seller_h).json()["id"]  # starts at 500, increment 50


def bid(client, headers, listing_id, amount):
    return client.post(f"/listings/{listing_id}/bids", json={"amount": amount}, headers=headers)


def save(client, headers, listing_id):
    return client.put(f"/listings/{listing_id}/watch", headers=headers)


def inbox(client, headers):
    return client.get("/notifications?limit=100", headers=headers).json()["items"]


def kinds(client, headers):
    return [n["type"] for n in reversed(inbox(client, headers))]


def closes_in(db, listing_id, **delta):
    listing = db.get(Listing, listing_id)
    listing.closes_at = utcnow() + timedelta(**delta)
    db.commit()


def expire(db, listing_id):
    closes_in(db, listing_id, seconds=-1)


# --- saving and listing ------------------------------------------------------


def test_save_and_unsave_an_auction(client, lid, alice_h):
    assert save(client, alice_h, lid).status_code == 204
    saved = client.get("/me/watchlist", headers=alice_h).json()
    assert [c["id"] for c in saved] == [lid] and saved[0]["title"] == "Hero cycle"
    assert client.delete(f"/listings/{lid}/watch", headers=alice_h).status_code == 204
    assert client.get("/me/watchlist", headers=alice_h).json() == []


def test_saving_twice_keeps_one_record_and_unsaving_something_unsaved_is_fine(client, db_session, lid, alice_h):
    save(client, alice_h, lid)
    assert save(client, alice_h, lid).status_code == 204
    assert db_session.query(Watch).count() == 1
    client.delete(f"/listings/{lid}/watch", headers=alice_h)
    assert client.delete(f"/listings/{lid}/watch", headers=alice_h).status_code == 204


def test_it_needs_a_login_and_a_real_listing(client, lid, alice_h):
    assert client.put(f"/listings/{lid}/watch").status_code == 401
    assert client.get("/me/watchlist").status_code == 401
    assert save(client, alice_h, 999).status_code == 404


def test_you_cannot_save_your_own_listing(client, lid, seller_h):
    assert save(client, seller_h, lid).status_code == 403


def test_an_ended_auction_cannot_be_newly_saved(client, db_session, lid, alice_h):
    expire(db_session, lid)
    assert save(client, alice_h, lid).status_code == 409


def test_everyones_list_is_their_own(client, lid, alice_h, bob_h):
    save(client, alice_h, lid)
    assert client.get("/me/watchlist", headers=bob_h).json() == []
    client.delete(f"/listings/{lid}/watch", headers=bob_h)  # Bob can't remove Alice's save
    assert len(client.get("/me/watchlist", headers=alice_h).json()) == 1


def test_open_auctions_come_first_soonest_closing_on_top_then_ended_ones(client, db_session, seller_h, alice_h):
    later, sooner, done = (create(client, seller_h, title=t).json()["id"] for t in ("Later", "Sooner", "Done"))
    for i in (later, sooner, done):
        save(client, alice_h, i)
    closes_in(db_session, later, hours=5)
    closes_in(db_session, sooner, hours=1)
    expire(db_session, done)
    close_due_listings(db_session)
    assert [c["title"] for c in client.get("/me/watchlist", headers=alice_h).json()] == ["Sooner", "Later", "Done"]


def test_the_list_is_capped(client, db_session, seller_h, alice_h, monkeypatch):
    monkeypatch.setattr(watchlist, "MAX_WATCHES", 2)
    ids = [create(client, seller_h, title=f"Item {i}").json()["id"] for i in range(3)]
    assert [save(client, alice_h, i).status_code for i in ids] == [204, 204, 409]


# --- reminders ---------------------------------------------------------------


def remind(db):
    return watchlist.send_due_reminders(db)


def test_a_far_off_auction_sends_nothing(client, db_session, lid, alice_h):
    save(client, alice_h, lid)
    closes_in(db_session, lid, hours=3)
    assert remind(db_session) == 0 and kinds(client, alice_h) == []


def test_a_watcher_is_reminded_once_inside_the_hour(client, db_session, lid, alice_h):
    save(client, alice_h, lid)
    closes_in(db_session, lid, minutes=50)
    assert remind(db_session) == 1
    [note] = inbox(client, alice_h)
    assert note["type"] == "reminder" and note["listing_id"] == lid
    assert "closes in 50 minutes" in note["title"] and "₹500" in note["body"]
    assert remind(db_session) == 0 and remind(db_session) == 0  # sweeping again repeats nothing
    assert len(inbox(client, alice_h)) == 1


def test_a_second_reminder_follows_at_five_minutes(client, db_session, lid, alice_h):
    save(client, alice_h, lid)
    closes_in(db_session, lid, minutes=50)
    remind(db_session)
    closes_in(db_session, lid, minutes=4, seconds=30)
    assert remind(db_session) == 1
    assert kinds(client, alice_h) == ["reminder", "reminder"]
    assert "5 minutes" in inbox(client, alice_h)[0]["title"]
    assert remind(db_session) == 0


def test_saving_late_gives_one_reminder_not_two(client, db_session, lid, alice_h):
    closes_in(db_session, lid, minutes=3)
    save(client, alice_h, lid)
    assert remind(db_session) == 1
    assert db_session.query(ClosingReminder).count() == 2  # both windows are marked as handled
    closes_in(db_session, lid, minutes=2)
    assert remind(db_session) == 0


def test_the_wording_depends_on_where_you_stand(client, db_session, lid, alice_h, bob_h, cara_h):
    bid(client, alice_h, lid, 500)
    bid(client, bob_h, lid, 550)  # Bob leads, Alice was outbid
    save(client, cara_h, lid)
    closes_in(db_session, lid, minutes=10)
    assert remind(db_session) == 3
    bodies = {n: inbox(client, h)[0]["body"] for n, h in (("alice", alice_h), ("bob", bob_h), ("cara", cara_h))}
    assert "You're leading at ₹550" in bodies["bob"]
    assert "not leading" in bodies["alice"] and "at least ₹600" in bodies["alice"]
    assert "Currently ₹550" in bodies["cara"]


def test_bidders_are_reminded_even_if_they_never_saved_it(client, db_session, lid, alice_h):
    bid(client, alice_h, lid, 500)
    closes_in(db_session, lid, minutes=30)
    assert remind(db_session) == 1 and "reminder" in kinds(client, alice_h)


def test_an_automatic_bidder_is_reminded_too(client, db_session, lid, alice_h):
    assert client.put(f"/listings/{lid}/auto-bid", json={"max_amount": 900}, headers=alice_h).status_code in (200, 201)
    closes_in(db_session, lid, minutes=30)
    assert remind(db_session) == 1


def test_the_seller_is_never_reminded(client, db_session, lid, seller_h, alice_h):
    save(client, alice_h, lid)
    closes_in(db_session, lid, minutes=30)
    remind(db_session)
    assert "reminder" not in kinds(client, seller_h)


def test_unsaving_stops_reminders(client, db_session, lid, alice_h):
    save(client, alice_h, lid)
    client.delete(f"/listings/{lid}/watch", headers=alice_h)
    closes_in(db_session, lid, minutes=30)
    assert remind(db_session) == 0


def test_ended_auctions_get_no_reminders(client, db_session, lid, alice_h):
    save(client, alice_h, lid)
    closes_in(db_session, lid, minutes=30)
    expire(db_session, lid)
    assert remind(db_session) == 0


def test_the_background_sweep_sends_reminders_and_results(client, db_session, lid, alice_h):
    from app.services.closer import sweep_once

    save(client, alice_h, lid)
    closes_in(db_session, lid, minutes=20)
    factory = lambda: type(db_session)(bind=db_session.get_bind())  # noqa: E731
    sweep_once(factory)
    assert kinds(client, alice_h) == ["reminder"]
    sweep_once(factory)
    assert kinds(client, alice_h) == ["reminder"]


# --- results -----------------------------------------------------------------


def test_everyone_who_followed_hears_how_it_ended(client, db_session, lid, seller_h, alice_h, bob_h, cara_h):
    bid(client, alice_h, lid, 500)
    bid(client, bob_h, lid, 550)
    save(client, cara_h, lid)
    expire(db_session, lid)
    close_due_listings(db_session)
    assert "won" in kinds(client, bob_h)
    assert "lost" in kinds(client, alice_h)
    [ended] = [n for n in inbox(client, cara_h) if n["type"] == "watch_ended"]
    assert "ended at ₹550" in ended["body"]


def test_a_watcher_who_also_bid_gets_the_bidder_message_only(client, db_session, lid, alice_h, bob_h):
    save(client, alice_h, lid)
    bid(client, alice_h, lid, 500)
    bid(client, bob_h, lid, 550)
    expire(db_session, lid)
    close_due_listings(db_session)
    assert "lost" in kinds(client, alice_h) and "watch_ended" not in kinds(client, alice_h)


def test_a_watcher_is_told_when_nobody_bid(client, db_session, lid, alice_h):
    save(client, alice_h, lid)
    expire(db_session, lid)
    close_due_listings(db_session)
    assert "no bids" in inbox(client, alice_h)[0]["body"]


def test_results_are_sent_once(client, db_session, lid, alice_h):
    save(client, alice_h, lid)
    expire(db_session, lid)
    close_due_listings(db_session)
    close_due_listings(db_session)
    assert kinds(client, alice_h) == ["watch_ended"]


def test_cancelling_tells_watchers(client, lid, seller_h, alice_h):
    save(client, alice_h, lid)
    client.post(f"/listings/{lid}/cancel", headers=seller_h)
    assert kinds(client, alice_h) == ["cancelled"]


def test_missed_updates_wait_for_an_offline_buyer(client, db_session, lid, alice_h):
    """Notifications are stored records: a buyer who was away finds them, unread, later."""
    save(client, alice_h, lid)
    closes_in(db_session, lid, minutes=30)
    remind(db_session)
    expire(db_session, lid)
    close_due_listings(db_session)
    feed = client.get("/notifications", headers=alice_h).json()
    assert [n["type"] for n in feed["items"]] == ["watch_ended", "reminder"] and feed["unread_count"] == 2
    assert db_session.query(Notification).filter_by(user_id=2, read_at=None).count() == 2  # stored, not just shown
