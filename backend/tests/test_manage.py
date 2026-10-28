import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.models import Bid, Listing, ListingStatus, User
from app.services.auction import BidError, begin_write, place_bid
from app.services.errors import ListingError
from app.services.listings import update_listing
from tests.conftest import auth_header
from tests.test_listings import JPEG, PNG, create, future


@pytest.fixture()
def seller_h(client):
    return auth_header(client, email="seller@campus.edu", name="Sam")


@pytest.fixture()
def other_h(client):
    return auth_header(client, email="other@campus.edu", name="Olu")


@pytest.fixture()
def bidder(db_session):
    user = User(email="bidder@campus.edu", password_hash="x", display_name="Bea")
    db_session.add(user)
    db_session.commit()
    return user


def new_listing(client, headers, **overrides):
    r = create(client, headers, **overrides)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def patch(client, headers, listing_id, **body):
    return client.patch(f"/listings/{listing_id}", json=body, headers=headers)


# --- editing ----------------------------------------------------------------


def test_edit_anything_before_the_first_bid(client, seller_h):
    lid = new_listing(client, seller_h)
    new_close = future(hours=6)
    r = patch(client, seller_h, lid, title="Hero Sprint", category="other", starting_price=800,
              min_increment=25, condition="fair", closes_at=new_close, description="Updated")
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["title"], body["category"], body["starting_price"]) == ("Hero Sprint", "other", 800)
    assert body["min_increment"] == 25 and body["condition"] == "fair" and body["description"] == "Updated"
    assert body["min_next_bid"] == 800  # the bid hint follows the new starting price


def test_partial_edit_leaves_other_fields_alone(client, seller_h):
    lid = new_listing(client, seller_h)
    body = patch(client, seller_h, lid, description="New text").json()
    assert body["description"] == "New text"
    assert body["title"] == "Hero cycle" and body["starting_price"] == 500


def test_after_a_bid_only_the_description_can_change(client, db_session, seller_h, bidder):
    lid = new_listing(client, seller_h)
    place_bid(db_session, lid, bidder.id, 500)

    assert patch(client, seller_h, lid, description="More details").status_code == 200

    for field, value in [("starting_price", 1), ("min_increment", 1), ("title", "Other"),
                         ("category", "books"), ("condition", "new"), ("closes_at", future(9))]:
        r = patch(client, seller_h, lid, **{field: value})
        assert r.status_code == 409, field
        assert field in r.json()["detail"]
    # A mixed edit is refused as a whole; nothing sneaks through.
    r = patch(client, seller_h, lid, description="sneaky", starting_price=1)
    assert r.status_code == 409
    body = client.get(f"/listings/{lid}").json()
    assert body["starting_price"] == 500 and body["description"] == "More details"


def test_edit_permissions_and_missing(client, seller_h, other_h):
    lid = new_listing(client, seller_h)
    assert client.patch(f"/listings/{lid}", json={"title": "x"}).status_code == 401
    assert patch(client, other_h, lid, title="Hijack").status_code == 403
    assert patch(client, seller_h, 999, title="x").status_code == 404
    assert client.get(f"/listings/{lid}").json()["title"] == "Hero cycle"


def test_edit_validation(client, seller_h):
    lid = new_listing(client, seller_h)
    assert patch(client, seller_h, lid).status_code == 422  # empty body
    assert patch(client, seller_h, lid, starting_price=0).status_code == 422
    assert patch(client, seller_h, lid, title="   ").status_code == 422
    assert patch(client, seller_h, lid, title=None).status_code == 422  # explicit null
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    assert patch(client, seller_h, lid, closes_at=past).status_code == 422
    assert patch(client, seller_h, lid, category="spaceship").status_code == 422


def test_cannot_edit_a_closed_listing(client, db_session, seller_h):
    lid = new_listing(client, seller_h)
    listing = db_session.get(Listing, lid)
    listing.closes_at = datetime.now(timezone.utc) - timedelta(minutes=1)  # expired, never swept
    db_session.commit()
    assert patch(client, seller_h, lid, description="too late").status_code == 409
    db_session.expire_all()
    assert db_session.get(Listing, lid).status == ListingStatus.unsold  # and it got closed


def test_edit_waits_for_an_in_flight_bid_then_sees_it(client, db_session, seller_h, bidder):
    """Deterministic proof the seller-action lock works.

    A bid transaction holds the write lock. An edit started meanwhile must wait for it, and
    once the bid commits the edit must see it and refuse. Without the lock, the edit would
    read "no bids yet" before the bid lands and happily overwrite the price afterwards.
    """
    lid = new_listing(client, seller_h, starting_price="100")
    engine = db_session.get_bind()
    seller_id = db_session.get(Listing, lid).seller_id
    result = {}

    def edit():
        with Session(engine) as s:
            try:
                update_listing(s, lid, seller_id, {"starting_price": 1000})
                result["edit"] = "ok"
            except ListingError as e:
                result["edit"] = e.code

    with Session(engine) as bid_tx:
        begin_write(bid_tx)  # the bid transaction takes the write lock...
        thread = threading.Thread(target=edit)
        thread.start()
        time.sleep(0.3)
        assert thread.is_alive(), "edit should be blocked while a bid holds the lock"
        bid = Bid(listing_id=lid, bidder_id=bidder.id, amount=100)
        bid_tx.add(bid)
        bid_tx.flush()
        listing = bid_tx.get(Listing, lid)
        listing.current_price, listing.leading_bid_id = 100, bid.id
        bid_tx.commit()  # ...and releases it here
    thread.join(timeout=10)

    assert result["edit"] == "conflict"  # saw the bid, so the price stayed frozen
    assert client.get(f"/listings/{lid}").json()["starting_price"] == 100


@pytest.mark.parametrize("attempt", range(12))
def test_edit_racing_a_bid_never_leaves_a_bid_under_the_new_price(attempt, client, db_session, seller_h, bidder):
    """Randomized smoke test: price edit and bid fired together must end in a legal state.

    The collision window is tiny, so this alone can't prove the lock; the deterministic test above does.
    """
    lid = new_listing(client, seller_h, starting_price="100")
    engine = db_session.get_bind()
    barrier = threading.Barrier(2)
    outcome = {}

    def do_bid():
        with Session(engine) as s:
            barrier.wait()
            try:
                place_bid(s, lid, bidder.id, 100)
                outcome["bid"] = "ok"
            except BidError as e:
                outcome["bid"] = e.code

    def do_edit():
        barrier.wait()
        outcome["edit"] = patch(client, seller_h, lid, starting_price=1000).status_code

    threads = [threading.Thread(target=do_bid), threading.Thread(target=do_edit)]
    [t.start() for t in threads]
    [t.join() for t in threads]

    body = client.get(f"/listings/{lid}").json()
    if outcome["edit"] == 200:  # edit won: the 100 bid must have been refused
        assert body["starting_price"] == 1000 and body["bid_count"] == 0 and outcome["bid"] == "too_low"
    else:  # bid won: edit refused, price frozen
        assert outcome["edit"] == 409 and body["starting_price"] == 100 and body["bid_count"] == 1


# --- cancelling -------------------------------------------------------------


def test_seller_cancels_even_with_bids(client, db_session, seller_h, bidder):
    lid = new_listing(client, seller_h)
    place_bid(db_session, lid, bidder.id, 500)
    r = client.post(f"/listings/{lid}/cancel", headers=seller_h)
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled" and r.json()["outcome_note"]
    assert r.json()["bid_count"] == 1  # history is kept
    with pytest.raises(BidError) as exc:
        place_bid(db_session, lid, bidder.id, 600)
    assert exc.value.code == "closed"


def test_cancel_permissions_and_state(client, seller_h, other_h):
    lid = new_listing(client, seller_h)
    assert client.post(f"/listings/{lid}/cancel").status_code == 401
    assert client.post(f"/listings/{lid}/cancel", headers=other_h).status_code == 403
    assert client.post("/listings/999/cancel", headers=seller_h).status_code == 404
    assert client.post(f"/listings/{lid}/cancel", headers=seller_h).status_code == 200
    assert client.post(f"/listings/{lid}/cancel", headers=seller_h).status_code == 409  # twice


def test_cancelled_listing_leaves_browse_but_is_findable_by_status(client, seller_h):
    lid = new_listing(client, seller_h)
    client.post(f"/listings/{lid}/cancel", headers=seller_h)
    assert client.get("/listings").json()["total"] == 0
    assert client.get("/listings", params={"status": "cancelled"}).json()["total"] == 1


# --- photos -----------------------------------------------------------------


def test_add_and_remove_photos(client, media_dir, seller_h):
    lid = new_listing(client, seller_h)
    r = client.post(f"/listings/{lid}/images", headers=seller_h,
                    files=[("images", ("b.jpg", JPEG, "image/jpeg"))])
    assert r.status_code == 200 and len(r.json()["images"]) == 2
    assert r.json()["images"][1].endswith(".jpg")  # new photo goes last

    folder = media_dir / "listings" / str(lid)
    assert len(list(folder.iterdir())) == 2
    first_name = r.json()["images"][0].rsplit("/", 1)[1]

    # Image ids start at 1 for this first listing: 1 = original, 2 = the one just added.
    r = client.delete(f"/listings/{lid}/images/1", headers=seller_h)
    assert r.status_code == 200 and len(r.json()["images"]) == 1
    assert not (folder / first_name).exists()  # file removed from disk too
    assert len(list(folder.iterdir())) == 1


def test_cannot_remove_the_last_photo_or_a_foreign_one(client, seller_h):
    a = new_listing(client, seller_h)  # image id 1
    b = new_listing(client, seller_h)  # image id 2
    assert client.delete(f"/listings/{a}/images/1", headers=seller_h).status_code == 409  # last photo
    assert client.delete(f"/listings/{a}/images/2", headers=seller_h).status_code == 404  # belongs to b
    assert client.delete(f"/listings/{a}/images/999", headers=seller_h).status_code == 404
    assert len(client.get(f"/listings/{b}").json()["images"]) == 1


def test_photo_limits_and_validation(client, seller_h):
    lid = new_listing(client, seller_h)
    four = [("images", (f"{i}.png", PNG, "image/png")) for i in range(4)]
    assert client.post(f"/listings/{lid}/images", headers=seller_h, files=four).status_code == 200  # now 5
    one_more = [("images", ("x.png", PNG, "image/png"))]
    assert client.post(f"/listings/{lid}/images", headers=seller_h, files=one_more).status_code == 422
    assert client.post(f"/listings/{lid}/images", headers=seller_h).status_code == 422  # no files


def test_fake_photo_rejected_and_nothing_left_on_disk(client, media_dir, seller_h):
    lid = new_listing(client, seller_h)
    fake = [("images", ("a.png", b"not an image", "image/png"))]
    assert client.post(f"/listings/{lid}/images", headers=seller_h, files=fake).status_code == 422
    assert len(list((media_dir / "listings" / str(lid)).iterdir())) == 1


def test_photo_changes_need_the_seller_and_work_after_bids(client, db_session, seller_h, other_h, bidder):
    lid = new_listing(client, seller_h)
    png = [("images", ("b.png", PNG, "image/png"))]
    assert client.post(f"/listings/{lid}/images", headers=other_h, files=png).status_code == 403
    assert client.delete(f"/listings/{lid}/images/1", headers=other_h).status_code == 403
    place_bid(db_session, lid, bidder.id, 500)
    assert client.post(f"/listings/{lid}/images", headers=seller_h, files=png).status_code == 200


# --- my listings / my bids --------------------------------------------------


def test_my_listings_shows_only_mine_in_every_status(client, seller_h, other_h):
    a = new_listing(client, seller_h, title="Mine A")
    new_listing(client, seller_h, title="Mine B")
    new_listing(client, other_h, title="Not mine")
    client.post(f"/listings/{a}/cancel", headers=seller_h)

    r = client.get("/me/listings", headers=seller_h)
    assert r.status_code == 200
    items = r.json()["items"]
    assert [i["title"] for i in items] == ["Mine B", "Mine A"]  # newest first
    assert {i["status"] for i in items} == {"active", "cancelled"}
    assert client.get("/me/listings").status_code == 401


def test_my_listings_paginates(client, seller_h):
    for i in range(3):
        new_listing(client, seller_h, title=f"L{i}")
    page = client.get("/me/listings", params={"limit": 2}, headers=seller_h).json()
    assert page["total"] == 3 and len(page["items"]) == 2


def test_my_bids_tracks_leading_and_outbid(client, db_session, seller_h, bidder):
    rival = User(email="rival@campus.edu", password_hash="x", display_name="Rey")
    db_session.add(rival)
    db_session.commit()
    a = new_listing(client, seller_h, title="A", starting_price="100")
    b = new_listing(client, seller_h, title="B", starting_price="100")
    c = new_listing(client, seller_h, title="C (never bid)")

    place_bid(db_session, a, bidder.id, 100)
    place_bid(db_session, a, rival.id, 150)
    place_bid(db_session, a, bidder.id, 200)  # my best on A is 200, and I'm back in front
    place_bid(db_session, b, bidder.id, 100)
    place_bid(db_session, b, rival.id, 200)  # I'm outbid on B

    from app.core.security import create_access_token
    h = {"Authorization": f"Bearer {create_access_token(bidder.id)}"}
    rows = {row["listing"]["title"]: row for row in client.get("/me/bids", headers=h).json()}
    assert set(rows) == {"A", "B"}  # C is excluded
    assert rows["A"]["my_highest_bid"] == 200 and rows["A"]["is_leading"] is True
    assert rows["B"]["my_highest_bid"] == 100 and rows["B"]["is_leading"] is False
    assert rows["B"]["listing"]["price"] == 200 and rows["B"]["listing"]["bid_count"] == 2
    assert client.get("/me/bids").status_code == 401


def test_my_bids_empty(client, seller_h):
    assert client.get("/me/bids", headers=seller_h).json() == []


# --- edit rules added in plan v3: window, caps, "edited at" marker ---------------


def test_edit_keeps_the_closing_window_and_price_caps(client, seller_h):
    lid = new_listing(client, seller_h)
    soon = (datetime.now(timezone.utc) + timedelta(minutes=3)).isoformat()
    far = (datetime.now(timezone.utc) + timedelta(days=45)).isoformat()
    assert patch(client, seller_h, lid, closes_at=soon).status_code == 422
    assert patch(client, seller_h, lid, closes_at=far).status_code == 422
    assert patch(client, seller_h, lid, starting_price=10_000_001).status_code == 422
    assert patch(client, seller_h, lid, min_increment=10_000_001).status_code == 422
    assert patch(client, seller_h, lid, starting_price=10_000_000).status_code == 200


def test_edited_at_is_empty_until_the_seller_changes_something(client, seller_h):
    lid = new_listing(client, seller_h)
    assert client.get(f"/listings/{lid}").json()["edited_at"] is None

    r = patch(client, seller_h, lid, description="Now with a bell")
    assert r.json()["edited_at"] is not None  # visible to everyone from now on
    assert client.get(f"/listings/{lid}").json()["edited_at"] == r.json()["edited_at"]


def test_photo_changes_also_count_as_edits(client, media_dir, seller_h):
    lid = new_listing(client, seller_h)
    r = client.post(f"/listings/{lid}/images", headers=seller_h, files=[("images", ("b.jpg", JPEG, "image/jpeg"))])
    assert r.json()["edited_at"] is not None
