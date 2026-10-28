"""The open-listing cap, rupee signs in outcome text, older notifications, and fingerprints for old photos."""

from datetime import timedelta
from pathlib import Path

import pytest

from app.core.clock import utcnow
from app.core.config import settings
from app.models import Listing, ListingImage
from app.services import listings
from app.services.auction import close_due_listings
from tests.conftest import auth_header
from tests.test_listings import PNG, create


@pytest.fixture()
def sam(client):
    return auth_header(client, email="seller@campus.edu", name="Sam")


def unique(n):
    return [("images", (f"{n}.png", PNG + str(n).encode(), "image/png"))]


# --- the cap ---------------------------------------------------------------------------------------------


def test_a_seller_cannot_have_more_open_auctions_than_the_cap(client, sam, monkeypatch):
    monkeypatch.setattr(settings, "max_open_listings", 3)
    codes = [create(client, sam, title=f"Item {i}", files=unique(i)).status_code for i in range(5)]
    assert codes == [201, 201, 201, 409, 409]
    assert "up to 3 auctions open at once" in create(client, sam, title="One more", files=unique(99)).json()["detail"]


def test_ending_or_cancelling_one_frees_a_slot_and_other_sellers_are_unaffected(client, sam, monkeypatch):
    monkeypatch.setattr(settings, "max_open_listings", 2)
    ids = [create(client, sam, title=f"Item {i}", files=unique(i)).json()["id"] for i in range(2)]
    assert create(client, sam, title="Third", files=unique(7)).status_code == 409
    client.post(f"/listings/{ids[0]}/cancel", headers=sam)
    assert create(client, sam, title="Third", files=unique(7)).status_code == 201
    other = auth_header(client, email="other@campus.edu", name="Olly")
    assert create(client, other, title="Mine", files=unique(8)).status_code == 201


def test_the_default_cap_is_generous():
    assert settings.max_open_listings >= 10


# --- rupee signs ------------------------------------------------------------------------------------------


def test_the_outcome_notes_show_rupees_with_grouping(client, db_session, sam):
    buyer = auth_header(client, email="buyer@campus.edu", name="Bea")
    lid = create(client, sam, starting_price="1500").json()["id"]
    client.post(f"/listings/{lid}/bids", json={"amount": 1500}, headers=buyer)
    db_session.get(Listing, lid).closes_at = utcnow() - timedelta(seconds=1)
    db_session.commit()
    close_due_listings(db_session)
    assert client.get(f"/listings/{lid}").json()["outcome_note"] == "Closed with a winning bid of ₹1,500"
    assert client.post(f"/listings/{lid}/approve", headers=sam).json()["outcome_note"].startswith("Approved by the seller at ₹1,500")
    assert client.post(f"/listings/{lid}/handover", headers=sam).json()["outcome_note"] == "Handed over; sale completed at ₹1,500"


# --- older notifications ---------------------------------------------------------------------------------


def test_older_notifications_can_be_paged_through(client, db_session, sam):
    from app.models import Notification, User

    user_id = db_session.query(User).filter_by(email="seller@campus.edu").one().id
    for i in range(7):
        db_session.add(Notification(user_id=user_id, type="x", title=f"n{i}", body=""))
    db_session.commit()
    first = client.get("/notifications?limit=3", headers=sam).json()
    assert [n["title"] for n in first["items"]] == ["n6", "n5", "n4"] and first["oldest_id"] == first["items"][-1]["id"]
    second = client.get(f"/notifications?limit=3&before_id={first['oldest_id']}", headers=sam).json()
    assert [n["title"] for n in second["items"]] == ["n3", "n2", "n1"]
    third = client.get(f"/notifications?limit=3&before_id={second['oldest_id']}", headers=sam).json()
    assert [n["title"] for n in third["items"]] == ["n0"]
    last = client.get(f"/notifications?limit=3&before_id={third['oldest_id']}", headers=sam).json()
    assert last["items"] == [] and last["oldest_id"] is None
    assert client.get("/notifications?before_id=0", headers=sam).status_code == 422


def test_paging_only_shows_my_own_notifications(client, db_session, sam):
    other = auth_header(client, email="other@campus.edu", name="Olly")
    from app.models import Notification, User

    oid = db_session.query(User).filter_by(email="other@campus.edu").one().id
    db_session.add(Notification(user_id=oid, type="x", title="theirs", body=""))
    db_session.commit()
    assert client.get("/notifications?before_id=999", headers=sam).json()["items"] == []
    assert len(client.get("/notifications?before_id=999", headers=other).json()["items"]) == 1


# --- fingerprints for photos from before the feature -------------------------------------------------------


def test_old_photos_get_a_fingerprint_from_the_stored_file_and_then_count_as_duplicates(client, db_session, sam, media_dir):
    first = create(client, sam, title="Hero cycle", files=unique(1), confirm_duplicate=None)
    assert first.status_code == 201
    image = db_session.query(ListingImage).one()
    image.sha256 = None  # as if uploaded before fingerprints existed
    db_session.commit()
    same_photo = create(client, sam, title="Totally different title", files=unique(1), confirm_duplicate=None)
    assert same_photo.status_code == 201  # not noticed yet: the old photo has no fingerprint

    assert listings.backfill_image_fingerprints(db_session) == 1
    assert db_session.query(ListingImage).filter(ListingImage.sha256.is_(None)).count() == 0
    again = create(client, sam, title="Yet another title", files=unique(1), confirm_duplicate=None)
    assert again.status_code == 409 and again.json()["detail"]["reason"] == "photo"


def test_backfill_skips_missing_files_and_does_nothing_twice(client, db_session, sam, media_dir):
    create(client, sam, files=unique(2))
    image = db_session.query(ListingImage).one()
    image.sha256 = None
    db_session.commit()
    (Path(settings.media_dir) / image.path).unlink()
    assert listings.backfill_image_fingerprints(db_session) == 0
    assert listings.backfill_image_fingerprints(db_session) == 0


def test_older_notes_without_a_rupee_sign_are_shown_with_one(client, db_session, sam):
    from app.services.listings import format_outcome_note

    assert format_outcome_note("Closed with a winning bid of 2800") == "Closed with a winning bid of ₹2,800"
    assert format_outcome_note("Approved by the seller at 1900; awaiting handover at Main Gate") == "Approved by the seller at ₹1,900; awaiting handover at Main Gate"
    assert format_outcome_note("Handed over; sale completed at 500") == "Handed over; sale completed at ₹500"
    assert format_outcome_note("Closed with a winning bid of ₹1,500") == "Closed with a winning bid of ₹1,500"  # already right
    assert format_outcome_note("Rejected by the seller: price 300 was too low") == "Rejected by the seller: price 300 was too low"
    assert format_outcome_note(None) is None
    lid = create(client, sam).json()["id"]
    listing = db_session.get(Listing, lid)
    listing.outcome_note = "Closed with a winning bid of 4002"
    db_session.commit()
    assert client.get(f"/listings/{lid}").json()["outcome_note"] == "Closed with a winning bid of ₹4,002"
