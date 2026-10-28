from app.core import security
from app.core.config import settings
from tests.conftest import auth_header, register


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["server_time"].endswith(("Z", "+00:00"))


def test_register_then_me(client):
    headers = auth_header(client)
    r = client.get("/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["email"] == "a@campus.edu"
    assert r.json()["display_name"] == "Asha"
    assert "password" not in r.text and "password_hash" not in r.text


def test_register_normalizes_email_and_rejects_duplicates(client):
    assert register(client, email="Asha@Campus.edu").status_code == 201
    assert register(client, email="asha@campus.EDU").status_code == 409


def test_register_validation(client):
    assert register(client, password="short").status_code == 422
    assert register(client, email="not-an-email").status_code == 422


def test_register_domain_restriction(client, monkeypatch):
    monkeypatch.setattr(settings, "allowed_email_domain", "campus.edu")
    assert register(client, email="x@gmail.com").status_code == 422
    assert register(client, email="x@campus.edu").status_code == 201


def test_login(client):
    register(client)
    ok = client.post("/auth/login", json={"email": "A@campus.edu", "password": "password123"})
    assert ok.status_code == 200
    bad_pw = client.post("/auth/login", json={"email": "a@campus.edu", "password": "wrongwrong"})
    assert bad_pw.status_code == 401
    unknown = client.post("/auth/login", json={"email": "z@campus.edu", "password": "password123"})
    assert unknown.status_code == 401
    # Same message for both, so emails can't be enumerated.
    assert bad_pw.json() == unknown.json()


def test_me_requires_valid_token(client):
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_expired_token_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "access_token_expire_minutes", -1)
    headers = auth_header(client)
    assert client.get("/me", headers=headers).status_code == 401


def test_password_hash_roundtrip():
    stored = security.hash_password("hunter2hunter2")
    assert stored != "hunter2hunter2"
    assert security.verify_password("hunter2hunter2", stored)
    assert not security.verify_password("nope", stored)
    assert not security.verify_password("x", "malformed")
