import asyncio
import time
from datetime import timedelta

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import utcnow
from app.models import Listing, ListingStatus
from app.services.auction import begin_write, place_bid
from app.services.closer import run_closer, sweep_once
from tests.test_auction import NOW, make_listing, make_user


@pytest.fixture()
def factory(db_session):
    return sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)


@pytest.fixture()
def seller(db_session):
    return make_user(db_session, "seller")


@pytest.fixture()
def bidder(db_session):
    return make_user(db_session, "bidder")


def status_of(db, listing_id):
    db.expire_all()
    return db.get(Listing, listing_id).status


def expire(db, listing):
    """Make a listing's time run out in real time while it is still marked active."""
    listing.closes_at = utcnow() - timedelta(seconds=1)
    db.commit()


def test_sweep_closes_only_what_is_due(db_session, factory, seller, bidder):
    with_bid = make_listing(db_session, seller)
    no_bid = make_listing(db_session, seller)
    later = make_listing(db_session, seller, closes_in=timedelta(hours=5))
    place_bid(db_session, with_bid.id, bidder.id, 100, now=NOW)

    assert sweep_once(factory, now=NOW + timedelta(hours=2)) == 2
    assert status_of(db_session, with_bid.id) == ListingStatus.pending_approval
    assert status_of(db_session, no_bid.id) == ListingStatus.unsold
    assert status_of(db_session, later.id) == ListingStatus.active
    assert sweep_once(factory, now=NOW + timedelta(hours=2)) == 0  # nothing left; safe to repeat


def test_idle_sweep_does_not_take_the_write_lock(db_session, factory, seller):
    """With nothing due, the sweep must not queue behind (or block) real bids."""
    make_listing(db_session, seller, closes_in=timedelta(hours=5))
    with Session(db_session.get_bind()) as holder:
        begin_write(holder)  # someone else is mid-write
        started = time.monotonic()
        assert sweep_once(factory, now=NOW) == 0
        # If it had tried to lock, SQLite would make it wait for the busy timeout (~5 s).
        assert time.monotonic() - started < 1.0


def test_background_loop_closes_expired_auctions(db_session, factory, seller, bidder):
    unsold = make_listing(db_session, seller)
    sold = make_listing(db_session, seller)
    place_bid(db_session, sold.id, bidder.id, 100, now=NOW)
    expire(db_session, unsold)
    expire(db_session, sold)

    async def scenario():
        task = asyncio.create_task(run_closer(factory, interval=0.05))
        for _ in range(100):  # up to ~5 s
            await asyncio.sleep(0.05)
            if status_of(db_session, unsold.id) != ListingStatus.active and \
               status_of(db_session, sold.id) != ListingStatus.active:
                break
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task  # cancelling stops the loop cleanly

    asyncio.run(scenario())
    assert status_of(db_session, unsold.id) == ListingStatus.unsold
    assert status_of(db_session, sold.id) == ListingStatus.pending_approval


def test_one_failed_sweep_does_not_kill_the_loop(db_session, factory, seller):
    listing = make_listing(db_session, seller)
    expire(db_session, listing)
    calls = {"n": 0}

    def flaky_factory():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("database hiccup")
        return factory()

    async def scenario():
        task = asyncio.create_task(run_closer(flaky_factory, interval=0.05))
        for _ in range(100):
            await asyncio.sleep(0.05)
            if status_of(db_session, listing.id) != ListingStatus.active:
                break
        assert not task.done()  # still alive after the failure
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert calls["n"] >= 2
    assert status_of(db_session, listing.id) == ListingStatus.unsold
