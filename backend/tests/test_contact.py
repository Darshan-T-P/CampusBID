"""Contact numbers: stored in one form, private, and shared only across an approved sale."""

from datetime import timedelta

import pytest

from app.core.clock import utcnow
from app.core.phone import clean_phone, normalize_phone
from app.models import Listing, User
from app.services.auction import close_due_listings
from tests.conftest import auth_header, register
from tests.test_listings import create


# --- the number itself -------------------------------------------------------


@pytest.mark.parametrize(
    "typed",
    ["9876543210", "98765 43210", "98765-43210", "098765 43210", "919876543210", "+91 98765 43210", "+91-98765-43210", " (+91) 98765.43210 "],
)
def test_the_usual_ways_of_typing_an_indian_mobile_all_become_one_form(typed):
    assert normalize_phone(typed) == "+919876543210"


def test_international_numbers_need_their_country_code():
    assert normalize_phone("+1 (415) 555-0123") == "+14155550123"
    assert normalize_phone("+44 7911 123456") == "+447911123456"


@pytest.mark.parametrize("typed", ["12345", "5876543210", "98765432", "+0123456789", "+12", "98765 4321a", "call me", "+91"])
def test_things_that_are_not_numbers_are_refused(typed):
    with pytest.raises(ValueError, match="valid mobile number"):
        normalize_phone(typed)


def test_blank_means_none():
    assert clean_phone(None) is None and clean_phone("   ") is None and clean_phone("98765 43210") == "+919876543210"


# --- giving and changing your own number --------------------------------------


def sign_up(client, phone, email="a@campus.edu", name="Asha"):
    body = {"email": email, "password": "password123", "display_name": name}
    if phone is not None:
        body["phone"] = phone
    return client.post("/auth/register", json=body)


def test_signing_up_with_a_number_stores_it_normalised_and_me_returns_it(client):
    token = sign_up(client, "98765 43210").json()["access_token"]
    assert client.get("/me", headers={"Authorization": f"Bearer {token}"}).json()["phone"] == "+919876543210"


def test_a_number_is_optional_and_a_bad_one_is_a_validation_error(client):
    assert sign_up(client, None).status_code == 201
    assert sign_up(client, "not a number", email="b@campus.edu").status_code == 422
    assert sign_up(client, "", email="c@campus.edu").status_code == 201  # blank = none


def test_profile_can_add_change_and_remove_it(client):
    h = auth_header(client)
    assert client.patch("/me", json={"phone": "+91 98765 43210"}, headers=h).json()["phone"] == "+919876543210"
    assert client.patch("/me", json={"phone": "91234 56789"}, headers=h).json()["phone"] == "+919123456789"
    assert client.patch("/me", json={"display_name": "Asha K"}, headers=h).json()["phone"] == "+919123456789"  # untouched
    assert client.patch("/me", json={"phone": ""}, headers=h).json()["phone"] is None
    assert client.patch("/me", json={"phone": "12"}, headers=h).status_code == 422


# --- who can see it -------------------------------------------------------------


@pytest.fixture()
def people(client):
    sam = sign_up(client, "98765 43210", "seller@campus.edu", "Sam").json()["access_token"]
    alice = sign_up(client, "91234 56789", "alice@campus.edu", "Alice").json()["access_token"]
    bob = sign_up(client, "99887 76655", "bob@campus.edu", "Bob").json()["access_token"]
    cara = sign_up(client, None, "cara@campus.edu", "Cara").json()["access_token"]
    return {k: {"Authorization": f"Bearer {v}"} for k, v in (("sam", sam), ("alice", alice), ("bob", bob), ("cara", cara))}


def sale(client, db, people, stage="reserved"):
    """A listing Alice won (Bob was outbid). `stage` is how far the sale has got."""
    lid = create(client, people["sam"]).json()["id"]
    client.post(f"/listings/{lid}/bids", json={"amount": 500}, headers=people["bob"])
    client.post(f"/listings/{lid}/bids", json={"amount": 550}, headers=people["alice"])
    listing = db.get(Listing, lid)
    listing.closes_at = utcnow() - timedelta(seconds=1)
    db.commit()
    close_due_listings(db)
    if stage == "reserved":
        assert client.post(f"/listings/{lid}/approve", headers=people["sam"]).status_code == 200
    return lid


def contact(client, headers, lid):
    return client.get(f"/listings/{lid}/contact", headers=headers)


def test_each_side_gets_the_other_sides_number_once_approved(client, db_session, people):
    lid = sale(client, db_session, people)
    to_buyer = contact(client, people["alice"], lid).json()
    to_seller = contact(client, people["sam"], lid).json()
    assert to_buyer == {"role": "seller", "name": "Sam", "phone": "+919876543210", "listing_title": "Hero cycle"}
    assert to_seller == {"role": "buyer", "name": "Alice", "phone": "+919123456789", "listing_title": "Hero cycle"}


def test_nothing_is_shared_before_the_seller_approves(client, db_session, people):
    lid = sale(client, db_session, people, stage="pending")
    assert contact(client, people["alice"], lid).status_code == 409
    assert contact(client, people["sam"], lid).status_code == 409


def test_nothing_is_shared_after_the_sale_is_over(client, db_session, people):
    lid = sale(client, db_session, people)
    client.post(f"/listings/{lid}/handover", headers=people["sam"])
    assert contact(client, people["alice"], lid).status_code == 409


def test_nothing_is_shared_while_bidding_is_open(client, people):
    lid = create(client, people["sam"]).json()["id"]
    client.post(f"/listings/{lid}/bids", json={"amount": 500}, headers=people["alice"])
    assert contact(client, people["alice"], lid).status_code == 409
    assert contact(client, people["sam"], lid).status_code == 409


def test_the_outbid_bidder_and_strangers_never_get_it(client, db_session, people):
    lid = sale(client, db_session, people)
    assert contact(client, people["bob"], lid).status_code == 403  # bid, but lost
    assert contact(client, people["cara"], lid).status_code == 403  # never involved
    assert client.get(f"/listings/{lid}/contact").status_code == 401  # not signed in
    assert contact(client, people["alice"], 999).status_code == 404


def test_a_missing_number_is_reported_not_invented(client, db_session):
    sam = {"Authorization": "Bearer " + sign_up(client, "98765 43210", "seller@campus.edu", "Sam").json()["access_token"]}
    cara = {"Authorization": "Bearer " + sign_up(client, None, "cara@campus.edu", "Cara").json()["access_token"]}
    lid = create(client, sam).json()["id"]
    client.post(f"/listings/{lid}/bids", json={"amount": 500}, headers=cara)
    listing = db_session.get(Listing, lid)
    listing.closes_at = utcnow() - timedelta(seconds=1)
    db_session.commit()
    close_due_listings(db_session)
    client.post(f"/listings/{lid}/approve", headers=sam)
    assert contact(client, sam, lid).json()["phone"] is None


def test_a_number_never_appears_anywhere_public(client, db_session, people):
    lid = sale(client, db_session, people)
    numbers = ("9876543210", "9123456789", "9988776655")
    for url in (f"/listings/{lid}", f"/listings/{lid}/bids", f"/listings/{lid}/auto-bids", "/listings"):
        assert not any(n in client.get(url).text for n in numbers), url
    for who in ("sam", "alice"):
        for url in ("/me/listings", "/me/bids", "/notifications", "/me/summary", "/me/watchlist"):
            text = client.get(url, headers=people[who]).text
            assert not any(n in text for n in numbers), (who, url)  # only /me itself returns your OWN number


def test_it_is_in_the_approval_message_that_the_contact_is_available(client, db_session, people):
    sale(client, db_session, people)
    approved = [n for n in client.get("/notifications", headers=people["alice"]).json()["items"] if n["type"] == "approved"][0]
    assert "contact number" in approved["body"] and "9876543210" not in approved["body"]


def test_the_lookup_is_rate_limited(client, db_session, people, monkeypatch):
    from app.core.config import settings
    from app.core.ratelimit import limiter

    lid = sale(client, db_session, people)
    limiter.reset()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    codes = [contact(client, people["alice"], lid).status_code for _ in range(62)]
    assert codes[:60] == [200] * 60 and codes[60:] == [429, 429]


def test_deleting_an_account_wipes_the_number(client, db_session):
    h = {"Authorization": "Bearer " + sign_up(client, "98765 43210", "seller@campus.edu", "Sam").json()["access_token"]}
    other = {"Authorization": "Bearer " + sign_up(client, None, "o@campus.edu", "Olly").json()["access_token"]}
    lid = create(client, h).json()["id"]
    client.post(f"/listings/{lid}/cancel", headers=h)  # a finished listing: the row has to stay, so it is anonymised
    assert client.post("/me/delete", json={"password": "password123"}, headers=h).status_code == 204
    assert db_session.get(User, 1).phone is None and db_session.get(User, 1).display_name == "Deleted user"
