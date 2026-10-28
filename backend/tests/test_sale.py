"""Sale workflow (plan A4): approve / reject / handover / pickup-failed."""

import threading
import time
from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.models import Listing, ListingStatus, User
from app.services import sale
from app.services.auction import begin_write, close_due_listings, place_bid
from app.services.errors import ListingError
from tests.conftest import auth_header
from tests.test_listings import create


@pytest.fixture()
def seller_h(client):
    return auth_header(client, email="seller@campus.edu", name="Sam")


@pytest.fixture()
def winner(db_session):
    user = User(email="winner@campus.edu", password_hash="x", display_name="Wendy", is_verified=True)
    db_session.add(user)
    db_session.commit()
    return user


def post(client, headers, listing_id, action, **kwargs):
    return client.post(f"/listings/{listing_id}/{action}", headers=headers, **kwargs)


def closed_listing(client, db_session, seller_h, winner, with_bid=True):
    """A listing whose auction just ended: pending_approval if it had a bid, else unsold."""
    lid = create(client, seller_h).json()["id"]
    if with_bid:
        place_bid(db_session, lid, winner.id, 500)
    listing = db_session.get(Listing, lid)
    close_due_listings(db_session, now=listing.closes_at)
    return lid


def status_of(client, lid):
    return client.get(f"/listings/{lid}").json()["status"]


# --- the legal path ---------------------------------------------------------


def test_full_sale_cycle_approve_then_handover(client, db_session, seller_h, winner):
    lid = closed_listing(client, db_session, seller_h, winner)
    assert status_of(client, lid) == "pending_approval"

    r = post(client, seller_h, lid, "approve")
    assert r.status_code == 200
    assert r.json()["status"] == "reserved" and "awaiting handover" in r.json()["outcome_note"]
    assert r.json()["leading_bidder"] == "Wendy"  # the seller knows who to meet

    r = post(client, seller_h, lid, "handover")
    assert r.status_code == 200
    assert r.json()["status"] == "completed" and "500" in r.json()["outcome_note"]


def test_reject_with_and_without_a_reason(client, db_session, seller_h, winner):
    a = closed_listing(client, db_session, seller_h, winner)
    r = post(client, seller_h, a, "reject", json={"reason": "Winner's account looks fake {price}"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert r.json()["outcome_note"] == "Rejected by the seller: Winner's account looks fake {price}"

    b = closed_listing(client, db_session, seller_h, winner)
    r = post(client, seller_h, b, "reject")  # no body at all
    assert r.status_code == 200 and r.json()["outcome_note"] == "Rejected by the seller"
    assert post(client, seller_h, closed_listing(client, db_session, seller_h, winner), "reject",
                json={"reason": "x" * 501}).status_code == 422  # too long


def test_pickup_failed_is_recorded(client, db_session, seller_h, winner):
    lid = closed_listing(client, db_session, seller_h, winner)
    post(client, seller_h, lid, "approve")
    r = post(client, seller_h, lid, "pickup-failed")
    assert r.status_code == 200
    assert r.json()["status"] == "failed_pickup" and "did not collect" in r.json()["outcome_note"]


# --- who may act ------------------------------------------------------------


def test_only_the_seller_may_decide(client, db_session, seller_h, winner):
    lid = closed_listing(client, db_session, seller_h, winner)
    stranger_h = auth_header(client, email="stranger@campus.edu", name="Stu")
    for action in ("approve", "reject", "handover", "pickup-failed"):
        assert post(client, stranger_h, lid, action).status_code == 403, action
        assert post(client, {}, lid, action).status_code == 401, action
    assert status_of(client, lid) == "pending_approval"  # nothing changed


def test_the_winner_cannot_approve_their_own_win(client, db_session, seller_h, winner):
    from app.core.security import create_access_token
    winner_h = {"Authorization": f"Bearer {create_access_token(winner.id)}"}
    lid = closed_listing(client, db_session, seller_h, winner)
    assert post(client, winner_h, lid, "approve").status_code == 403


def test_unknown_listing_is_404(client, seller_h):
    for action in ("approve", "reject", "handover", "pickup-failed"):
        assert post(client, seller_h, 999, action).status_code == 404


# --- illegal moves are refused ---------------------------------------------


def test_cannot_act_while_the_auction_is_still_running(client, seller_h):
    lid = create(client, seller_h).json()["id"]
    for action in ("approve", "reject", "handover", "pickup-failed"):
        r = post(client, seller_h, lid, action)
        assert r.status_code == 409 and "still open" in r.json()["detail"], action


def test_cannot_approve_an_unsold_listing(client, db_session, seller_h, winner):
    lid = closed_listing(client, db_session, seller_h, winner, with_bid=False)
    assert status_of(client, lid) == "unsold"
    r = post(client, seller_h, lid, "approve")
    assert r.status_code == 409 and "no bids" in r.json()["detail"]


def test_cannot_act_on_a_cancelled_listing(client, seller_h):
    lid = create(client, seller_h).json()["id"]
    post(client, seller_h, lid, "cancel")
    assert post(client, seller_h, lid, "approve").status_code == 409


def test_steps_cannot_be_skipped_or_repeated(client, db_session, seller_h, winner):
    lid = closed_listing(client, db_session, seller_h, winner)
    assert post(client, seller_h, lid, "handover").status_code == 409  # not approved yet
    assert post(client, seller_h, lid, "pickup-failed").status_code == 409
    assert post(client, seller_h, lid, "approve").status_code == 200
    assert post(client, seller_h, lid, "approve").status_code == 409  # double-click
    assert post(client, seller_h, lid, "reject").status_code == 409  # can't change their mind
    assert post(client, seller_h, lid, "handover").status_code == 200
    assert post(client, seller_h, lid, "handover").status_code == 409


@pytest.mark.parametrize("path", [("reject",), ("approve", "pickup-failed")])
def test_finished_sales_are_final(client, db_session, seller_h, winner, path):
    lid = closed_listing(client, db_session, seller_h, winner)
    for action in path:
        assert post(client, seller_h, lid, action).status_code == 200
    final = status_of(client, lid)
    assert final in ("rejected", "failed_pickup")
    for action in ("approve", "reject", "handover", "pickup-failed"):
        assert post(client, seller_h, lid, action).status_code == 409, action
    assert status_of(client, lid) == final


# --- timing -----------------------------------------------------------------


def test_approving_right_after_the_deadline_works_even_if_the_closer_has_not_run(
    client, db_session, seller_h, winner
):
    lid = create(client, seller_h).json()["id"]
    place_bid(db_session, lid, winner.id, 500)
    listing = db_session.get(Listing, lid)
    listing.closes_at = utcnow() - timedelta(seconds=1)  # time is up; status still "active"
    db_session.commit()

    r = post(client, seller_h, lid, "approve")
    assert r.status_code == 200 and r.json()["status"] == "reserved"


# --- concurrency (C7) -------------------------------------------------------


def test_approve_waits_for_an_in_flight_decision_then_refuses(client, db_session, seller_h, winner):
    """Deterministic proof the lock works: a reject commits while an approve is waiting.

    Without the lock the approve would read the stale 'pending_approval' and overwrite the
    rejection, ending 'reserved' after the seller had already rejected.
    """
    lid = closed_listing(client, db_session, seller_h, winner)
    engine = db_session.get_bind()
    seller_id = db_session.get(Listing, lid).seller_id
    result = {}

    def approve():
        with Session(engine) as s:
            try:
                sale.approve(s, lid, seller_id)
                result["approve"] = "ok"
            except ListingError as e:
                result["approve"] = e.code

    with Session(engine) as other_tab:
        begin_write(other_tab)  # the other tab's reject holds the write lock...
        thread = threading.Thread(target=approve)
        thread.start()
        time.sleep(0.3)
        assert thread.is_alive(), "approve should wait behind the in-flight reject"
        other_tab.get(Listing, lid).status = ListingStatus.rejected
        other_tab.commit()  # ...and finishes here
    thread.join(timeout=10)

    assert result["approve"] == "conflict"
    assert status_of(client, lid) == "rejected"


@pytest.mark.parametrize("attempt", range(6))
def test_approve_and_reject_from_two_tabs_exactly_one_wins(attempt, client, db_session, seller_h, winner):
    lid = closed_listing(client, db_session, seller_h, winner)
    barrier = threading.Barrier(2)
    out = {}

    def go(action):
        barrier.wait()
        out[action] = post(client, seller_h, lid, action).status_code

    threads = [threading.Thread(target=go, args=(a,)) for a in ("approve", "reject")]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert sorted(out.values()) == [200, 409]
    winner_action = "approve" if out["approve"] == 200 else "reject"
    assert status_of(client, lid) == {"approve": "reserved", "reject": "rejected"}[winner_action]


# --- visibility -------------------------------------------------------------


def test_outcomes_show_up_in_my_listings_and_my_bids(client, db_session, seller_h, winner):
    from app.core.security import create_access_token
    winner_h = {"Authorization": f"Bearer {create_access_token(winner.id)}"}
    lid = closed_listing(client, db_session, seller_h, winner)
    post(client, seller_h, lid, "approve")

    mine = client.get("/me/listings", headers=seller_h).json()["items"][0]
    assert mine["id"] == lid and mine["status"] == "reserved"
    bids = client.get("/me/bids", headers=winner_h).json()
    assert bids[0]["listing"]["status"] == "reserved" and bids[0]["is_leading"] is True  # the buyer sees they won
    assert client.get("/listings").json()["total"] == 0  # no longer in the open browse list
    assert client.get("/listings", params={"status": "reserved"}).json()["total"] == 1
