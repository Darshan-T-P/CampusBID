"""Posting the same item twice: the seller is asked "is this a second item?" instead of silently getting a copy."""

from datetime import timedelta

import pytest

from app.core.clock import utcnow
from app.models import Listing, ListingStatus
from tests.conftest import auth_header
from tests.test_listings import JPEG, PNG, create


@pytest.fixture()
def sam(client):
    return auth_header(client, email="seller@campus.edu", name="Sam")


_photo_counter = iter(range(10_000))


def post(client, headers, **overrides):
    """A listing post that does NOT pre-confirm, the way the real form behaves the first time.

    Each call gets its own photo unless the test passes one, so only the thing under test can look like a duplicate."""
    overrides.setdefault("confirm_duplicate", None)
    if "files" not in overrides:
        overrides["files"] = [("images", ("p.png", PNG + str(next(_photo_counter)).encode(), "image/png"))]
    return create(client, headers, **overrides)


def test_the_same_title_is_flagged_with_what_already_exists(client, sam):
    first = post(client, sam, title="Hero cycle").json()
    r = post(client, sam, title="Hero cycle")
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["code"] == "possible_duplicate" and detail["reason"] == "title"
    assert detail["existing"] == {"id": first["id"], "title": "Hero cycle", "status": "active", "price": 500}
    assert "already have an open listing" in detail["message"]


def test_nothing_is_created_when_it_is_flagged(client, db_session, sam):
    post(client, sam, title="Hero cycle")
    post(client, sam, title="Hero cycle")
    assert db_session.query(Listing).count() == 1


def test_case_spacing_and_punctuation_do_not_hide_a_duplicate(client, sam):
    post(client, sam, title="Hero Cycle (21-gear)")
    assert post(client, sam, title="  hero   cycle 21 gear!! ").status_code == 409


def test_a_near_identical_title_in_the_same_category_is_flagged(client, sam):
    post(client, sam, title="Hero Sprint 21 speed cycle")
    r = post(client, sam, title="Hero Sprint 21-speed cycles")
    assert r.status_code == 409 and r.json()["detail"]["reason"] in ("title", "similar")


def test_a_similar_title_in_another_category_is_fine(client, sam):
    post(client, sam, title="Hero Sprint 21 speed cycle", category="cycle")
    assert post(client, sam, title="Hero Sprint 21 speed cycles", category="other").status_code == 201


def test_a_different_item_is_fine(client, sam):
    post(client, sam, title="Hero cycle")
    assert post(client, sam, title="Casio calculator", category="calculator", files=[("images", ("b.png", PNG + b"b", "image/png"))]).status_code == 201


def test_the_same_photo_is_flagged_even_under_a_different_title(client, sam):
    post(client, sam, title="Hero cycle", files=[("images", ("a.png", PNG + b"unique-1", "image/png"))])
    r = post(client, sam, title="Blue bike for sale", files=[("images", ("copy.png", PNG + b"unique-1", "image/png"))])
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "photo"
    assert "photos is already on your open listing" in r.json()["detail"]["message"]


def test_confirming_that_it_is_a_second_item_posts_it(client, db_session, sam):
    post(client, sam, title="Hero cycle")
    assert post(client, sam, title="Hero cycle").status_code == 409
    r = post(client, sam, title="Hero cycle", confirm_duplicate="true")
    assert r.status_code == 201 and db_session.query(Listing).count() == 2


def test_other_sellers_never_clash(client, sam):
    other = auth_header(client, email="other@campus.edu", name="Olly")
    post(client, sam, title="Hero cycle", files=[("images", ("a.png", PNG + b"same", "image/png"))])
    assert post(client, other, title="Hero cycle", files=[("images", ("a.png", PNG + b"same", "image/png"))]).status_code == 201


@pytest.mark.parametrize("status", [ListingStatus.cancelled, ListingStatus.unsold, ListingStatus.completed, ListingStatus.rejected])
def test_finished_listings_do_not_count_so_relisting_is_easy(client, db_session, sam, status):
    lid = post(client, sam, title="Hero cycle").json()["id"]
    db_session.get(Listing, lid).status = status
    db_session.commit()
    assert post(client, sam, title="Hero cycle").status_code == 201


@pytest.mark.parametrize("status", [ListingStatus.pending_approval, ListingStatus.reserved])
def test_a_sale_in_progress_still_counts(client, db_session, sam, status):
    lid = post(client, sam, title="Hero cycle").json()["id"]
    listing = db_session.get(Listing, lid)
    listing.status = status
    db_session.commit()
    r = post(client, sam, title="Hero cycle")
    assert r.status_code == 409 and r.json()["detail"]["existing"]["status"] == status.value


def test_the_fingerprint_is_stored_with_each_photo(client, db_session, sam):
    from app.models import ListingImage

    post(client, sam, files=[("images", ("a.jpg", JPEG + b"zz", "image/jpeg"))])
    [image] = db_session.query(ListingImage).all()
    assert image.sha256 and len(image.sha256) == 64


def test_the_time_a_listing_has_been_up_does_not_matter(client, db_session, sam):
    lid = post(client, sam, title="Hero cycle").json()["id"]
    db_session.get(Listing, lid).created_at = utcnow() - timedelta(days=20)
    db_session.commit()
    assert post(client, sam, title="Hero cycle").status_code == 409
