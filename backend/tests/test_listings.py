from datetime import datetime, timedelta, timezone

from app.models import Category, Condition, Listing, ListingStatus, User
from tests.conftest import auth_header

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


def future(hours=2):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def form(**overrides):
    data = {
        "title": "Hero cycle",
        "category": "cycle",
        "condition": "good",
        "description": "Barely used, 21 gears",
        "starting_price": "500",
        "min_increment": "50",
        "closes_at": future(),
    }
    data.update(overrides)
    return {k: v for k, v in data.items() if v is not None}


def create(client, headers, files=None, **overrides):
    files = [("images", ("a.png", PNG, "image/png"))] if files is None else files
    return client.post("/listings", data=form(**overrides), files=files, headers=headers)


def test_create_listing_returns_public_detail(client):
    headers = auth_header(client)
    r = create(client, headers)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == "Hero cycle"
    assert body["status"] == "active"
    assert body["current_price"] is None
    assert body["min_next_bid"] == 500  # first bid must meet the starting price
    assert body["bid_count"] == 0 and body["leading_bidder"] is None
    assert body["seller"] == {"id": 1, "display_name": "Asha"}
    assert len(body["images"]) == 1 and body["images"][0].startswith("/media/listings/1/")
    assert len(body["image_ids"]) == 1  # ids line up with the URLs, so one photo can be removed
    assert body["images"][0].endswith(".png")
    assert "email" not in r.text  # sellers are identified by display name only


def test_photos_are_written_under_server_chosen_names(client, media_dir):
    headers = auth_header(client)
    r = create(client, headers, files=[("images", ("../../evil.png", PNG, "image/png"))])
    assert r.status_code == 201
    stored = list((media_dir / "listings" / "1").iterdir())
    assert len(stored) == 1
    assert "evil" not in stored[0].name  # the client's filename is ignored


def test_create_requires_login(client):
    assert create(client, headers={}).status_code == 401


def test_closes_at_must_be_in_the_future(client):
    headers = auth_header(client)
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    r = create(client, headers, closes_at=past)
    assert r.status_code == 422
    assert "at least 10 minutes" in r.json()["detail"]


def test_closing_window_is_10_minutes_to_30_days(client):
    headers = auth_header(client)

    def attempt(**delta):
        return create(client, headers, closes_at=(datetime.now(timezone.utc) + timedelta(**delta)).isoformat())

    assert attempt(minutes=5).status_code == 422  # too short
    assert attempt(minutes=11).status_code == 201  # just long enough
    assert attempt(days=29).status_code == 201
    too_long = attempt(days=31)
    assert too_long.status_code == 422 and "at most 30 days" in too_long.json()["detail"]


def test_closes_at_needs_a_timezone(client):
    headers = auth_header(client)
    naive = (datetime.now() + timedelta(hours=2)).replace(tzinfo=None).isoformat()
    r = create(client, headers, closes_at=naive)
    assert r.status_code == 422
    assert "timezone" in r.json()["detail"]


def test_price_rules(client):
    headers = auth_header(client)
    assert create(client, headers, starting_price="0").status_code == 422
    assert create(client, headers, min_increment="0").status_code == 422


def test_price_caps(client):
    headers = auth_header(client)
    assert create(client, headers, starting_price="10000000").status_code == 201  # the cap itself is fine
    assert create(client, headers, starting_price="10000001").status_code == 422
    assert create(client, headers, min_increment="10000001").status_code == 422


def test_blank_title_rejected(client):
    headers = auth_header(client)
    assert create(client, headers, title="   ").status_code == 422


def test_photo_count_limits(client, media_dir):
    headers = auth_header(client)
    assert create(client, headers, files=[]).status_code == 422  # none
    six = [("images", (f"{i}.png", PNG, "image/png")) for i in range(6)]
    assert create(client, headers, files=six).status_code == 422  # too many
    five = [("images", (f"{i}.jpg", JPEG, "image/jpeg")) for i in range(5)]
    assert create(client, headers, files=five).status_code == 201


def test_photo_must_really_be_an_image(client):
    headers = auth_header(client)
    fake = [("images", ("a.png", b"just some text", "image/png"))]  # lies about its type
    r = create(client, headers, files=fake)
    assert r.status_code == 422
    assert "JPEG, PNG or WebP" in r.json()["detail"]


def test_oversized_photo_rejected_and_nothing_saved(client, media_dir):
    headers = auth_header(client)
    big = [("images", ("a.png", PNG + b"\x00" * (5 * 1024 * 1024), "image/png"))]
    assert create(client, headers, files=big).status_code == 422
    assert not (media_dir / "listings").exists()


def test_get_listing_is_public(client):
    headers = auth_header(client)
    listing_id = create(client, headers).json()["id"]
    r = client.get(f"/listings/{listing_id}")  # no auth header
    assert r.status_code == 200
    assert r.json()["id"] == listing_id
    assert r.json()["server_time"]


def test_get_unknown_listing_404(client):
    assert client.get("/listings/999").status_code == 404


def test_reading_an_expired_listing_closes_it(client, db_session):
    seller = User(email="s@campus.edu", password_hash="x", display_name="Sam")
    db_session.add(seller)
    db_session.commit()
    listing = Listing(
        seller_id=seller.id,
        title="Old calculator",
        category=Category.calculator,
        condition=Condition.fair,
        starting_price=100,
        closes_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    db_session.add(listing)
    db_session.commit()

    r = client.get(f"/listings/{listing.id}")
    assert r.json()["status"] == ListingStatus.unsold.value
    assert r.json()["min_next_bid"] is None  # no more bidding
    db_session.expire_all()
    assert db_session.get(Listing, listing.id).status == ListingStatus.unsold  # persisted
