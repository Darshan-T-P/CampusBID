import threading
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Bid, Category, Condition, Listing, ListingStatus, User
from app.services.auction import BidError, close_due_listings, min_valid_bid, place_bid

NOW = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)


def make_user(db, name):
    user = User(email=f"{name}@campus.edu", password_hash="x", display_name=name)
    db.add(user)
    db.commit()
    return user


def make_listing(db, seller, *, start=100, inc=10, closes_in=timedelta(hours=1)):
    listing = Listing(
        seller_id=seller.id,
        title="Hero cycle",
        category=Category.cycle,
        condition=Condition.good,
        starting_price=start,
        min_increment=inc,
        closes_at=NOW + closes_in,
    )
    db.add(listing)
    db.commit()
    return listing


@pytest.fixture()
def seller(db_session):
    return make_user(db_session, "seller")


@pytest.fixture()
def alice(db_session):
    return make_user(db_session, "alice")


@pytest.fixture()
def bob(db_session):
    return make_user(db_session, "bob")


@pytest.fixture()
def listing(db_session, seller):
    return make_listing(db_session, seller)


def bids_for(db, listing_id):
    db.expire_all()
    return db.scalars(select(Bid).where(Bid.listing_id == listing_id).order_by(Bid.id)).all()


# --- bid validity -----------------------------------------------------------


def test_first_bid_must_meet_starting_price(db_session, listing, alice):
    with pytest.raises(BidError) as exc:
        place_bid(db_session, listing.id, alice.id, 99, now=NOW)
    assert exc.value.code == "too_low"
    assert exc.value.min_bid == 100
    assert bids_for(db_session, listing.id) == []


def test_first_bid_at_starting_price_is_accepted(db_session, listing, alice):
    bid = place_bid(db_session, listing.id, alice.id, 100, now=NOW)
    db_session.refresh(listing)
    assert listing.current_price == 100
    assert listing.leading_bid_id == bid.id
    assert bid.is_auto is False


def test_next_bid_must_clear_increment(db_session, listing, alice, bob):
    place_bid(db_session, listing.id, alice.id, 100, now=NOW)
    assert min_valid_bid(listing) == 110
    with pytest.raises(BidError) as exc:
        place_bid(db_session, listing.id, bob.id, 109, now=NOW)
    assert exc.value.code == "too_low" and exc.value.min_bid == 110
    place_bid(db_session, listing.id, bob.id, 110, now=NOW)
    db_session.refresh(listing)
    assert listing.current_price == 110


def test_equal_bid_is_rejected_so_earliest_wins(db_session, listing, alice, bob):
    first = place_bid(db_session, listing.id, alice.id, 150, now=NOW)
    with pytest.raises(BidError):
        place_bid(db_session, listing.id, bob.id, 150, now=NOW)
    db_session.refresh(listing)
    assert listing.leading_bid_id == first.id


def test_leader_cannot_bid_against_themselves(db_session, listing, alice):
    place_bid(db_session, listing.id, alice.id, 100, now=NOW)
    with pytest.raises(BidError) as exc:
        place_bid(db_session, listing.id, alice.id, 120, now=NOW)
    assert exc.value.code == "already_leading"
    assert [b.amount for b in bids_for(db_session, listing.id)] == [100]  # nothing was recorded


def test_a_bidder_may_bid_again_once_outbid(db_session, listing, alice, bob):
    place_bid(db_session, listing.id, alice.id, 100, now=NOW)
    place_bid(db_session, listing.id, bob.id, 110, now=NOW)
    place_bid(db_session, listing.id, alice.id, 120, now=NOW)  # Alice is no longer the leader
    assert [b.amount for b in bids_for(db_session, listing.id)] == [100, 110, 120]


def test_seller_cannot_bid_on_own_listing(db_session, listing, seller):
    with pytest.raises(BidError) as exc:
        place_bid(db_session, listing.id, seller.id, 500, now=NOW)
    assert exc.value.code == "own_listing"


def test_unknown_listing(db_session, alice):
    with pytest.raises(BidError) as exc:
        place_bid(db_session, 9999, alice.id, 100, now=NOW)
    assert exc.value.code == "not_found"


@pytest.mark.parametrize(
    "status", [ListingStatus.cancelled, ListingStatus.pending_approval, ListingStatus.reserved]
)
def test_non_active_listing_rejects_bids(db_session, listing, alice, status):
    listing.status = status
    db_session.commit()
    with pytest.raises(BidError) as exc:
        place_bid(db_session, listing.id, alice.id, 100, now=NOW)
    assert exc.value.code == "closed"


# --- time -------------------------------------------------------------------


def test_bid_just_before_close_is_accepted(db_session, listing, alice):
    place_bid(db_session, listing.id, alice.id, 100, now=listing.closes_at - timedelta(seconds=1))
    assert len(bids_for(db_session, listing.id)) == 1


def test_bid_at_exact_close_time_is_rejected(db_session, listing, alice):
    with pytest.raises(BidError) as exc:
        place_bid(db_session, listing.id, alice.id, 100, now=listing.closes_at)
    assert exc.value.code == "closed"


def test_late_bid_rejected_even_if_sweeper_never_ran(db_session, listing, alice, bob):
    place_bid(db_session, listing.id, alice.id, 100, now=NOW)
    late = listing.closes_at + timedelta(seconds=5)
    with pytest.raises(BidError) as exc:
        place_bid(db_session, listing.id, bob.id, 999, now=late)
    assert exc.value.code == "closed"
    # The lazy close was persisted, and the late bid did not land.
    db_session.refresh(listing)
    assert listing.status == ListingStatus.pending_approval
    assert [b.amount for b in bids_for(db_session, listing.id)] == [100]


# --- closing ----------------------------------------------------------------


def test_close_with_bids_goes_to_pending_approval(db_session, listing, alice, bob):
    place_bid(db_session, listing.id, alice.id, 100, now=NOW)
    top = place_bid(db_session, listing.id, bob.id, 130, now=NOW)
    closed = close_due_listings(db_session, now=listing.closes_at)
    assert [l.id for l in closed] == [listing.id]
    db_session.refresh(listing)
    assert listing.status == ListingStatus.pending_approval
    assert listing.leading_bid_id == top.id
    assert "130" in listing.outcome_note


def test_close_without_bids_is_unsold(db_session, listing):
    close_due_listings(db_session, now=listing.closes_at + timedelta(minutes=1))
    db_session.refresh(listing)
    assert listing.status == ListingStatus.unsold
    assert listing.outcome_note


def test_sweep_ignores_listings_not_yet_due_and_is_idempotent(db_session, seller, alice):
    soon = make_listing(db_session, seller, closes_in=timedelta(minutes=5))
    later = make_listing(db_session, seller, closes_in=timedelta(hours=5))
    place_bid(db_session, soon.id, alice.id, 100, now=NOW)

    sweep_at = NOW + timedelta(minutes=10)
    assert [l.id for l in close_due_listings(db_session, now=sweep_at)] == [soon.id]
    assert close_due_listings(db_session, now=sweep_at) == []
    db_session.refresh(later)
    assert later.status == ListingStatus.active


# --- concurrency ------------------------------------------------------------


def _race(engine, listing_id, jobs):
    """Run (bidder_id, amount) jobs simultaneously, each in its own session."""
    barrier = threading.Barrier(len(jobs))
    results = []

    def run(bidder_id, amount):
        with Session(engine) as session:
            barrier.wait()
            try:
                place_bid(session, listing_id, bidder_id, amount, now=NOW)
                results.append("ok")
            except BidError as e:
                results.append(e.code)

    threads = [threading.Thread(target=run, args=job) for job in jobs]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def test_racing_identical_bids_only_one_wins(db_session, listing, seller):
    engine = db_session.get_bind()
    bidders = [make_user(db_session, f"racer{i}") for i in range(8)]
    results = _race(engine, listing.id, [(b.id, 100) for b in bidders])

    assert results.count("ok") == 1
    assert results.count("too_low") == 7
    assert len(bids_for(db_session, listing.id)) == 1


def test_racing_different_bids_leave_consistent_state(db_session, listing, seller):
    engine = db_session.get_bind()
    bidders = [make_user(db_session, f"racer{i}") for i in range(8)]
    amounts = [100 + 10 * i for i in range(8)]
    _race(engine, listing.id, list(zip((b.id for b in bidders), amounts)))

    stored = bids_for(db_session, listing.id)
    placed = [b.amount for b in stored]
    # Whatever order they landed in, every accepted bid cleared the increment over the last.
    assert placed == sorted(placed)
    assert all(b - a >= 10 for a, b in zip(placed, placed[1:]))
    db_session.refresh(listing)
    assert listing.current_price == placed[-1] == max(amounts)
    assert listing.leading_bid_id == stored[-1].id
