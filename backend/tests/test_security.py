"""Security hardening: password storage, token checks, request limits, headers."""

import time

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core import security
from app.core.config import settings
from app.core.ratelimit import limiter
from app.main import app, check_startup_settings
from app.models import User
from tests.conftest import auth_header, register
from tests.test_listings import create


# --- password storage -------------------------------------------------------


def test_hashes_are_salted_and_record_their_own_settings():
    a, b = security.hash_password("hunter2hunter2"), security.hash_password("hunter2hunter2")
    assert a != b  # a fresh salt each time: equal passwords don't look equal in the database
    assert a.startswith("scrypt$") and a.count("$") == 5
    assert "hunter2" not in a
    assert security.verify_password("hunter2hunter2", a) and not security.verify_password("wrong", a)


def test_garbage_hashes_never_verify_or_crash():
    for junk in ["", "x", "scrypt$1$2", "zz$zz", "scrypt$abc$8$1$00$00", "a$b$c$d$e$f"]:
        assert security.verify_password("anything", junk) is False


def test_original_format_hashes_still_work_and_are_flagged_for_upgrade(monkeypatch):
    import hashlib, os

    salt = os.urandom(16)  # the format used before the upgrade: 'salt$hash', fixed N=2**14
    legacy = f"{salt.hex()}${hashlib.scrypt(b'oldpassword', salt=salt, n=2**14, r=8, p=1).hex()}"
    assert security.verify_password("oldpassword", legacy)
    assert security.needs_rehash(legacy)
    assert not security.needs_rehash(security.hash_password("x"))


def test_login_upgrades_a_weak_hash_in_place(client, db_session):
    import hashlib, os

    register(client, email="old@campus.edu", password="password123")
    salt = os.urandom(16)
    user = db_session.query(User).one()
    user.password_hash = f"{salt.hex()}${hashlib.scrypt(b'password123', salt=salt, n=2**14, r=8, p=1).hex()}"
    db_session.commit()

    assert client.post("/auth/login", json={"email": "old@campus.edu", "password": "password123"}).status_code == 200
    db_session.expire_all()
    upgraded = db_session.query(User).one().password_hash
    assert upgraded.startswith("scrypt$")  # now stored with current settings
    assert client.post("/auth/login", json={"email": "old@campus.edu", "password": "password123"}).status_code == 200


def test_unknown_email_costs_the_same_work_as_a_wrong_password(client, monkeypatch):
    """Otherwise the response time reveals which emails have accounts."""
    register(client, email="real@campus.edu")
    calls = []
    real_verify = security.verify_password
    monkeypatch.setattr(security, "verify_password", lambda p, s: (calls.append(1), real_verify(p, s))[1])
    from app.api.routes import auth as auth_routes
    monkeypatch.setattr(auth_routes, "verify_password", security.verify_password)

    client.post("/auth/login", json={"email": "real@campus.edu", "password": "wrong-password"})
    client.post("/auth/login", json={"email": "ghost@campus.edu", "password": "wrong-password"})
    assert len(calls) == 2  # a hash was computed for BOTH attempts


# --- tokens -----------------------------------------------------------------


def _token(**claims):
    return jwt.encode(claims, settings.secret_key, algorithm="HS256")


def test_token_without_expiry_is_rejected():
    assert security.decode_access_token(_token(sub="1")) is None
    assert security.decode_access_token(_token(sub="1", exp=time.time() + 600)) == 1


def test_token_without_subject_or_with_wrong_signature_or_algorithm_is_rejected():
    assert security.decode_access_token(_token(exp=time.time() + 600)) is None
    forged = jwt.encode({"sub": "1", "exp": time.time() + 600}, "some-other-secret-key-that-is-long-enough", algorithm="HS256")
    assert security.decode_access_token(forged) is None
    assert security.decode_access_token(jwt.encode({"sub": "1", "exp": time.time() + 600}, settings.secret_key, algorithm="HS512")) is None
    assert security.decode_access_token("not.a.jwt") is None


# --- startup refuses weak configuration -------------------------------------


@pytest.mark.parametrize("weak", ["short", "dev-secret-change-me-please-use-32-bytes-min", "change-me-to-a-long-random-string-of-32+-chars"])
def test_a_weak_or_placeholder_secret_stops_the_app_outside_dev_mode(monkeypatch, weak):
    monkeypatch.setattr(settings, "dev_mode", False)
    monkeypatch.setattr(settings, "allowed_email_domains", "college.edu")
    monkeypatch.setattr(settings, "secret_key", weak)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        check_startup_settings()


def test_a_real_secret_is_accepted_and_dev_mode_tolerates_the_default(monkeypatch):
    monkeypatch.setattr(settings, "allowed_email_domains", "college.edu")
    monkeypatch.setattr(settings, "dev_mode", False)
    monkeypatch.setattr(settings, "secret_key", "x9Qm2-Lp7vTn4wKzR8aYc1BdHe5GfJu0S3oVi6NtXq")
    check_startup_settings()
    monkeypatch.setattr(settings, "dev_mode", True)
    monkeypatch.setattr(settings, "secret_key", "dev-secret-change-me-please-use-32-bytes-min")
    check_startup_settings()


# --- headers and request size -----------------------------------------------


def test_security_headers_are_on_every_response(client):
    h = client.get("/health").headers
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert h["referrer-policy"] == "no-referrer"
    assert h["cache-control"] == "no-store"  # personal API data must not be cached
    assert "frame-ancestors 'none'" in h["content-security-policy"]
    assert "strict-transport-security" not in h  # only sent over https


def test_errors_carry_the_headers_too(client):
    r = client.get("/me")  # 401
    assert r.status_code == 401 and r.headers["x-content-type-options"] == "nosniff"


def test_hsts_is_added_over_https():
    secure = TestClient(app, base_url="https://testserver")
    assert "max-age=" in secure.get("/health").headers["strict-transport-security"]


def test_photos_are_served_with_nosniff_but_stay_cacheable(client, media_dir):
    headers = auth_header(client)
    url = create(client, headers).json()["images"][0]
    # the test client serves /media from the default folder; the header logic is what matters
    r = client.get(url)
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("cache-control") != "no-store"


def test_oversized_requests_are_refused_up_front(client, monkeypatch):
    monkeypatch.setattr(settings, "max_request_bytes", 1000)
    headers = auth_header(client)
    r = client.post("/auth/login", headers={"content-type": "application/json"}, content=b"{" + b" " * 5000 + b"}")
    assert r.status_code == 413 and r.json() == {"detail": "Request too large"}
    assert r.headers["x-content-type-options"] == "nosniff"
    assert client.get("/me", headers=headers).status_code == 200  # normal-sized requests are untouched


def test_a_chunked_upload_that_hides_its_size_is_still_stopped(client, monkeypatch):
    monkeypatch.setattr(settings, "max_request_bytes", 1000)

    def chunks():
        for _ in range(10):
            yield b"x" * 500  # no Content-Length: the server has to count as it reads

    r = client.post("/auth/login", headers={"content-type": "application/json"}, content=chunks())
    assert r.status_code == 413


def test_the_api_docs_are_hidden_outside_dev_mode(monkeypatch):
    import importlib
    from app import main

    monkeypatch.setattr(settings, "dev_mode", False)
    deployed = importlib.reload(main).app
    try:
        c = TestClient(deployed)
        assert c.get("/docs").status_code == 404 and c.get("/openapi.json").status_code == 404
    finally:
        monkeypatch.setattr(settings, "dev_mode", True)
        importlib.reload(main)


# --- rate limits on the write endpoints -------------------------------------


@pytest.fixture()
def limits_on(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    limiter.reset()


def test_bidding_is_rate_limited_per_user(client, limits_on):
    seller = auth_header(client, email="seller@campus.edu")
    lid = create(client, seller).json()["id"]
    bidder = auth_header(client, email="b@campus.edu")
    codes = [client.post(f"/listings/{lid}/bids", json={"amount": 1}, headers=bidder).status_code for _ in range(70)]
    assert codes[:60].count(429) == 0 and 429 in codes[60:]
    # one noisy user doesn't lock out everyone else
    other = auth_header(client, email="c@campus.edu")
    assert client.post(f"/listings/{lid}/bids", json={"amount": 500}, headers=other).status_code == 201


def test_listing_creation_is_rate_limited_per_user(client, limits_on):
    headers = auth_header(client)
    codes = [create(client, headers).status_code for _ in range(22)]
    assert codes[:20] == [201] * 20 and codes[20:] == [429, 429]
