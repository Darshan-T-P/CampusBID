"""Live auction updates: the stream must not starve the API, and events must reach watchers."""

import asyncio
import threading
from datetime import timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from app.api.routes import listings as listing_routes
from app.core.clock import utcnow
from app.core.events import AuctionBroadcaster, broadcaster
from app.models import Listing
from app.services.closer import sweep_once
from tests.conftest import auth_header
from tests.test_listings import create


@pytest.fixture()
def loop():
    """An event loop we drive by hand, standing in for the server's loop that owns the stream queues."""
    lp = asyncio.new_event_loop()
    yield lp
    lp.close()


def watch(loop, listing_id):
    return loop.run_until_complete(broadcaster.subscribe(listing_id))


def next_event(loop, q, seconds=2):
    return loop.run_until_complete(asyncio.wait_for(q.get(), seconds))


# --- the connection pool ---------------------------------------------------------------------------


def test_an_open_stream_holds_no_database_connection(client, db_session, monkeypatch):
    """Fifteen open auction pages used to freeze every other request, because each stream kept a connection."""
    monkeypatch.setattr(listing_routes, "STREAM_PING_SECONDS", 0.2)  # so the stream ends quickly when the test closes it
    lid = create(client, auth_header(client, email="seller@campus.edu", name="Sam")).json()["id"]
    db_session.rollback()
    engine = db_session.get_bind()
    with client.stream("GET", f"/listings/{lid}/stream") as response:
        first = next(response.iter_lines())
        assert first == "event: connect"
        assert engine.pool.checkedout() == 0  # the stream is open, and nothing is borrowed from the pool


def test_streaming_an_unknown_listing_is_a_404(client):
    assert client.get("/listings/999/stream").status_code == 404


# --- the broadcaster ----------------------------------------------------------------------------------


def test_an_event_published_from_another_thread_arrives_at_once():
    async def scenario():
        hub = AuctionBroadcaster()
        q = await hub.subscribe(5)
        threading.Timer(0.1, lambda: hub.publish_nowait("bid", {"n": 1}, listing_id=5)).start()
        return await asyncio.wait_for(q.get(), 1.0)

    assert asyncio.run(scenario())["data"] == {"n": 1}


def test_only_the_watchers_of_that_auction_get_it():
    async def scenario():
        hub = AuctionBroadcaster()
        mine, other = await hub.subscribe(1), await hub.subscribe(2)
        hub.publish_nowait("bid", {}, listing_id=1)
        await asyncio.sleep(0.05)
        return mine.qsize(), other.qsize()

    assert asyncio.run(scenario()) == (1, 0)


# --- auctions announce their own ending ---------------------------------------------------------------


def test_the_closer_tells_watchers_the_moment_an_auction_ends(client, db_session, loop):
    lid = create(client, auth_header(client, email="seller@campus.edu", name="Sam")).json()["id"]
    q = watch(loop, lid)
    db_session.get(Listing, lid).closes_at = utcnow() - timedelta(seconds=1)
    db_session.commit()
    sweep_once(lambda: sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)())
    event = next_event(loop, q)
    assert event["event"] == "closed" and event["data"] == {"listing_id": lid, "status": "unsold"}


def test_sale_steps_and_cancelling_are_pushed_with_the_new_state(client, db_session, loop):
    sam = auth_header(client, email="seller@campus.edu", name="Sam")
    alice = auth_header(client, email="alice@campus.edu", name="Alice")
    lid = create(client, sam).json()["id"]
    client.post(f"/listings/{lid}/bids", json={"amount": 500}, headers=alice)
    q = watch(loop, lid)
    db_session.get(Listing, lid).closes_at = utcnow() - timedelta(seconds=1)
    db_session.commit()
    sweep_once(lambda: sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)())
    assert next_event(loop, q)["event"] == "closed"
    client.post(f"/listings/{lid}/approve", headers=sam)
    event = next_event(loop, q)
    assert event["event"] == "status" and event["data"]["listing"]["status"] == "reserved"

    other = create(client, sam, title="Second").json()["id"]
    q2 = watch(loop, other)
    client.post(f"/listings/{other}/cancel", headers=sam)
    assert next_event(loop, q2)["data"]["listing"]["status"] == "cancelled"
