"""Campus-only trust (plan A0). Test names carry the plan's edge-case ids (T1-T7)."""

from datetime import timedelta

import pytest

from app.core.clock import utcnow
from app.core.config import settings
from app.core.ratelimit import limiter
from app.main import check_startup_settings
from app.models import EmailVerification, User
from app.services import accounts
from app.services.errors import AccountError
from tests.conftest import register
from tests.test_listings import create

CAMPUS = "campus.edu"


@pytest.fixture()
def campus(monkeypatch):
    monkeypatch.setattr(settings, "allowed_email_domains", CAMPUS)


@pytest.fixture()
def codes(monkeypatch):
    """Capture verification codes instead of 'sending' them."""
    sent = []
    monkeypatch.setattr(accounts, "deliver_code", lambda email, code: sent.append((email, code)))
    return sent


@pytest.fixture()
def real_verification(monkeypatch, codes):
    """New accounts start UNverified and must use the emailed code."""
    monkeypatch.setattr(settings, "auto_verify", False)
    monkeypatch.setattr(settings, "verification_resend_cooldown_seconds", 0)
    return codes


def signup(client, email="asha@campus.edu"):
    r = register(client, email=email)
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# --- T1 / T3: which emails may register -------------------------------------


def test_T1_only_campus_domains_may_register(client, campus):
    assert register(client, email="x@gmail.com").status_code == 422
    assert register(client, email="x@campus.edu").status_code == 201


def test_T1_several_domains_and_subdomains(client, monkeypatch):
    monkeypatch.setattr(settings, "allowed_email_domains", "college.edu, mail.uni.edu")
    assert register(client, email="a@college.edu").status_code == 201
    assert register(client, email="b@mail.uni.edu").status_code == 201
    assert register(client, email="c@cs.college.edu").status_code == 201  # a real subdomain
    assert register(client, email="d@uni.edu").status_code == 422  # only mail.uni.edu was listed


def test_T1_app_refuses_to_start_without_domains_unless_dev_mode(monkeypatch):
    monkeypatch.setattr(settings, "allowed_email_domains", "")
    monkeypatch.setattr(settings, "dev_mode", False)
    with pytest.raises(RuntimeError, match="ALLOWED_EMAIL_DOMAINS"):
        check_startup_settings()
    monkeypatch.setattr(settings, "dev_mode", True)
    check_startup_settings()  # fine in dev mode
    monkeypatch.setattr(settings, "dev_mode", False)
    monkeypatch.setattr(settings, "allowed_email_domains", "college.edu")
    monkeypatch.setattr(settings, "secret_key", "k" * 40)
    check_startup_settings()  # fine once a domain and a real secret are configured


@pytest.mark.parametrize(
    "email",
    [
        "x@evilcampus.edu",  # suffix trick
        "x@campus.edu.evil.com",  # prefix trick
        "x@notcampus.edu",
        "x@campus.edu@evil.com",  # two @ signs
        "x@campus.edu.",  # trailing dot
    ],
)
def test_T3_lookalike_domains_are_refused(client, campus, email):
    assert register(client, email=email).status_code == 422


# --- T4: one mailbox, one account -------------------------------------------


def test_T4_plus_tags_and_case_collapse_to_one_account(client, campus):
    assert register(client, email="Asha+shop@Campus.edu").status_code == 201
    assert register(client, email="asha@campus.edu").status_code == 409
    assert register(client, email="ASHA+other@campus.edu").status_code == 409


def test_T4_login_works_with_any_spelling_of_the_same_mailbox(client, campus):
    register(client, email="asha@campus.edu", password="password123")
    for spelling in ("Asha@Campus.edu", "asha+x@campus.edu", " asha@campus.edu "):
        r = client.post("/auth/login", json={"email": spelling, "password": "password123"})
        assert r.status_code == 200, spelling


def test_T4_stored_email_is_the_normalized_form(client, db_session, campus):
    register(client, email="Asha+shop@Campus.edu")
    assert db_session.query(User).one().email == "asha@campus.edu"


# --- T2: email verification --------------------------------------------------


def test_T2_unverified_user_can_browse_but_not_list_or_bid(client, real_verification):
    headers = signup(client)
    assert client.get("/me", headers=headers).json()["is_verified"] is False
    assert client.get("/listings").status_code == 200  # browsing is open

    r = create(client, headers)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "email_not_verified"
    r = client.post("/listings/1/bids", json={"amount": 100}, headers=headers)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "email_not_verified"


def test_T2_correct_code_verifies_and_unlocks_listing(client, real_verification):
    headers = signup(client)
    email, code = real_verification[-1]
    assert email == "asha@campus.edu" and len(code) == 6 and code.isdigit()

    r = client.post("/auth/verify", json={"code": code}, headers=headers)
    assert r.status_code == 200 and r.json()["is_verified"] is True
    assert create(client, headers).status_code == 201  # now allowed


def test_T2_register_response_says_whether_verification_is_needed(client, real_verification):
    assert register(client).json()["is_verified"] is False


def test_T2_wrong_code_counts_attempts_then_locks_out(client, real_verification, monkeypatch):
    headers = signup(client)
    _, code = real_verification[-1]
    wrong = "000000" if code != "000000" else "111111"
    for left in (4, 3, 2, 1, 0):
        r = client.post("/auth/verify", json={"code": wrong}, headers=headers)
        assert r.status_code == 422 and f"{left} attempt" in r.json()["detail"]
    # Out of attempts: even the RIGHT code is refused until a new one is requested.
    r = client.post("/auth/verify", json={"code": code}, headers=headers)
    assert r.status_code == 429


def test_T2_new_code_resets_attempts_and_invalidates_the_old_one(client, real_verification):
    headers = signup(client)
    _, old = real_verification[-1]
    client.post("/auth/verify", json={"code": "999999" if old != "999999" else "888888"}, headers=headers)

    assert client.post("/auth/resend-code", headers=headers).status_code == 204
    _, new = real_verification[-1]
    assert len(real_verification) == 2
    if new != old:
        assert client.post("/auth/verify", json={"code": old}, headers=headers).status_code == 422
    assert client.post("/auth/verify", json={"code": new}, headers=headers).status_code == 200


def test_T2_code_expires_after_ten_minutes(client, db_session, real_verification):
    signup(client)
    user = db_session.query(User).one()
    _, code = real_verification[-1]
    later = utcnow() + timedelta(minutes=10, seconds=1)
    with pytest.raises(AccountError, match="expired"):
        accounts.verify_code(db_session, user, code, now=later)
    just_in_time = utcnow() + timedelta(minutes=9)
    accounts.verify_code(db_session, user, code, now=just_in_time)
    assert user.is_verified


def test_T2_code_is_never_stored_in_plain_text(client, db_session, real_verification):
    signup(client)
    _, code = real_verification[-1]
    record = db_session.query(EmailVerification).one()
    assert code not in record.code_hash and len(record.code_hash) == 64


def test_T2_resend_has_a_cooldown(client, real_verification, monkeypatch):
    monkeypatch.setattr(settings, "verification_resend_cooldown_seconds", 60)
    headers = signup(client)
    r = client.post("/auth/resend-code", headers=headers)  # asked again right after signup
    assert r.status_code == 429 and "wait" in r.json()["detail"]


def test_T2_verification_edge_cases(client, real_verification):
    assert client.post("/auth/verify", json={"code": "123456"}).status_code == 401  # needs login
    headers = signup(client)
    assert client.post("/auth/verify", json={"code": "12345"}, headers=headers).status_code == 422  # format
    assert client.post("/auth/verify", json={"code": "abcdef"}, headers=headers).status_code == 422
    _, code = real_verification[-1]
    assert client.post("/auth/verify", json={"code": code}, headers=headers).status_code == 200
    assert client.post("/auth/verify", json={"code": code}, headers=headers).status_code == 200  # twice is harmless
    assert client.post("/auth/resend-code", headers=headers).status_code == 409  # nothing to resend


def test_T2_auto_verify_mode_skips_the_email_step(client):
    # Default test setup has auto_verify on: the demo shortcut.
    headers = signup(client)
    assert client.get("/me", headers=headers).json()["is_verified"] is True


# --- T5: rate limits ---------------------------------------------------------


@pytest.fixture()
def limits_on(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    limiter.reset()


def test_T5_login_attempts_on_one_account_are_limited(client, limits_on):
    register(client, email="asha@campus.edu", password="password123")
    statuses = [
        client.post("/auth/login", json={"email": "asha@campus.edu", "password": "wrong-password"}).status_code
        for _ in range(12)
    ]
    assert statuses[:10] == [401] * 10
    assert statuses[10:] == [429, 429]
    blocked = client.post("/auth/login", json={"email": "asha@campus.edu", "password": "password123"})
    assert blocked.status_code == 429 and int(blocked.headers["Retry-After"]) > 0  # even the right one waits


def test_T5_login_message_does_not_reveal_whether_the_email_exists(client, limits_on):
    register(client, email="asha@campus.edu")
    known = client.post("/auth/login", json={"email": "asha@campus.edu", "password": "nope-nope"})
    unknown = client.post("/auth/login", json={"email": "nobody@campus.edu", "password": "nope-nope"})
    assert known.status_code == unknown.status_code == 401
    assert known.json() == unknown.json()


def test_T5_signup_spam_from_one_address_is_limited(client, limits_on):
    codes_ = [register(client, email=f"user{i}@campus.edu").status_code for i in range(12)]
    assert codes_[:10] == [201] * 10 and codes_[10:] == [429, 429]


def test_T5_verification_guessing_is_limited_per_user(client, real_verification, limits_on):
    headers = signup(client)
    # 15 tries per window across codes/resends; the 16th is blocked before it is even checked.
    results = [client.post("/auth/verify", json={"code": "000000"}, headers=headers).status_code for _ in range(16)]
    assert results[-1] == 429


# --- T7: tokens --------------------------------------------------------------


def test_T7_token_of_a_deleted_user_stops_working(client, db_session):
    headers = signup(client)
    assert client.get("/me", headers=headers).status_code == 200
    db_session.delete(db_session.query(User).one())
    db_session.commit()
    assert client.get("/me", headers=headers).status_code == 401


# --- only institutional (.edu) addresses ------------------------------------


@pytest.mark.parametrize("email", ["a@gmail.com", "a@college.ac.in", "a@edu.com", "a@college.edu.com", "a@campus.education"])
def test_only_dot_edu_addresses_may_register(client, email):
    r = register(client, email=email)
    assert r.status_code == 422 and ".edu" in r.json()["detail"]


def test_dot_edu_subdomains_are_fine(client):
    assert register(client, email="a@cs.kongu.edu").status_code == 201


def test_the_suffix_rule_can_be_turned_off(client, monkeypatch):
    monkeypatch.setattr(settings, "required_email_suffix", "")
    assert register(client, email="a@college.ac.in").status_code == 201


# --- year and department ----------------------------------------------------


def test_year_and_department_are_stored_and_returned_on_the_profile(client):
    r = client.post("/auth/register", json={
        "email": "ann@campus.edu", "password": "password123", "display_name": "Ann",
        "department": "  Computer Science ", "year_of_study": 3,
    })
    assert r.status_code == 201
    me = client.get("/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).json()
    assert me["department"] == "Computer Science" and me["year_of_study"] == 3


def test_year_and_department_are_optional_for_the_api(client):
    r = register(client)
    me = client.get("/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).json()
    assert me["department"] is None and me["year_of_study"] is None


@pytest.mark.parametrize("bad", [{"year_of_study": 0}, {"year_of_study": 7}, {"year_of_study": "second"}, {"department": "x" * 81}])
def test_bad_year_or_department_is_rejected(client, bad):
    body = {"email": "ann@campus.edu", "password": "password123", "display_name": "Ann", **bad}
    assert client.post("/auth/register", json=body).status_code == 422


def test_a_listings_seller_shows_department_and_year_but_never_an_email(client):
    r = client.post("/auth/register", json={
        "email": "sam@campus.edu", "password": "password123", "display_name": "Sam",
        "department": "Mechanical", "year_of_study": 4,
    })
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    listing = create(client, headers).json()
    assert {k: listing["seller"][k] for k in ("id", "display_name", "department", "year_of_study")} == {"id": 1, "display_name": "Sam", "department": "Mechanical", "year_of_study": 4}
    assert "@" not in client.get(f"/listings/{listing['id']}").text
