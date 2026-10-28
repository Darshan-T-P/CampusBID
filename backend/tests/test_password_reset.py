"""Forgot password: a code by email, a new password, no hint about who has an account."""

import time
from datetime import timedelta

import jwt
import pytest

from app.core.clock import utcnow
from app.core.config import settings
from app.core.ratelimit import limiter
from app.models import PasswordReset, User
from app.services import accounts
from app.services.errors import AccountError
from tests.conftest import register


@pytest.fixture()
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(accounts, "deliver_code", lambda e, c: sent.append(("verify", e, c)))
    monkeypatch.setattr(accounts, "deliver_reset_code", lambda e, c: sent.append(("reset", e, c)))
    monkeypatch.setattr(accounts, "deliver_password_changed", lambda e: sent.append(("changed", e, None)))
    return sent


@pytest.fixture()
def account(client):
    register(client, email="asha@campus.edu", password="old-password-1")


def forgot(client, email="asha@campus.edu"):
    return client.post("/auth/forgot-password", json={"email": email})


def reset(client, code, new="new-password-2", email="asha@campus.edu"):
    return client.post("/auth/reset-password", json={"email": email, "code": code, "new_password": new})


def reset_codes(outbox):
    return [c for kind, _, c in outbox if kind == "reset"]


# --- asking for a code ------------------------------------------------------


def test_a_known_email_gets_one_code(client, account, outbox):
    r = forgot(client)
    assert r.status_code == 202 and "we've sent a code" in r.json()["message"]
    assert [(k, to) for k, to, _ in outbox] == [("reset", "asha@campus.edu")]
    assert len(reset_codes(outbox)[0]) == 6


def test_an_unknown_email_gets_exactly_the_same_answer_and_nothing_is_sent(client, account, outbox):
    known, unknown = forgot(client), forgot(client, "ghost@campus.edu")
    assert (known.status_code, known.json()) == (unknown.status_code, unknown.json())  # no way to tell them apart
    assert [to for _, to, _ in outbox] == ["asha@campus.edu"]


def test_the_address_is_normalized_like_at_sign_up(client, account, outbox):
    assert forgot(client, "  Asha+shopping@CAMPUS.edu ").status_code == 202
    assert [to for _, to, _ in outbox] == ["asha@campus.edu"]


def test_asking_again_straight_away_is_answered_the_same_but_sends_nothing(client, account, outbox, monkeypatch):
    monkeypatch.setattr(settings, "verification_resend_cooldown_seconds", 60)
    forgot(client)
    again = forgot(client)
    assert again.status_code == 202 and len(reset_codes(outbox)) == 1  # the cooldown is silent: it must not reveal anything


def test_a_malformed_address_is_a_validation_error(client):
    assert forgot(client, "not-an-email").status_code == 422


def test_how_many_emails_one_inbox_can_be_sent_is_capped(client, account, outbox, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "verification_resend_cooldown_seconds", 0)
    limiter.reset()
    codes = [forgot(client).status_code for _ in range(5)]
    assert codes == [202, 202, 202, 429, 429]


def test_the_code_is_stored_only_as_a_hash(client, account, outbox, db_session):
    forgot(client)
    record = db_session.query(PasswordReset).one()
    assert reset_codes(outbox)[0] not in record.code_hash and len(record.code_hash) == 64


# --- using the code ---------------------------------------------------------


def test_the_code_sets_a_new_password_and_signs_the_person_in(client, account, outbox):
    forgot(client)
    r = reset(client, reset_codes(outbox)[0])
    assert r.status_code == 200 and r.json()["access_token"] and r.json()["is_verified"] is True
    assert client.get("/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).json()["email"] == "asha@campus.edu"
    assert client.post("/auth/login", json={"email": "asha@campus.edu", "password": "new-password-2"}).status_code == 200
    assert client.post("/auth/login", json={"email": "asha@campus.edu", "password": "old-password-1"}).status_code == 401
    assert ("changed", "asha@campus.edu", None) in outbox  # the owner is told


def test_resetting_signs_out_every_older_session(client, account, outbox):
    old = jwt.encode({"sub": "1", "iat": int(time.time()) - 3600, "exp": int(time.time()) + 3600}, settings.secret_key, algorithm="HS256")
    assert client.get("/me", headers={"Authorization": f"Bearer {old}"}).status_code == 200
    forgot(client)
    reset(client, reset_codes(outbox)[0])
    assert client.get("/me", headers={"Authorization": f"Bearer {old}"}).status_code == 401  # a stolen token dies too


def test_a_code_works_only_once(client, account, outbox):
    forgot(client)
    code = reset_codes(outbox)[0]
    assert reset(client, code).status_code == 200
    assert reset(client, code, new="another-password-3").status_code == 422


def test_a_wrong_code_is_refused_and_five_wrong_tries_lock_it(client, account, outbox):
    forgot(client)
    real = reset_codes(outbox)[0]
    wrong = "000000" if real != "000000" else "111111"
    assert [reset(client, wrong).status_code for _ in range(5)] == [422] * 5
    assert reset(client, real).status_code == 429  # even the right code is refused now


def test_a_fresh_code_clears_the_lockout(client, account, outbox, monkeypatch):
    monkeypatch.setattr(settings, "verification_resend_cooldown_seconds", 0)
    forgot(client)
    for _ in range(5):
        reset(client, "000000")
    forgot(client)
    assert reset(client, reset_codes(outbox)[-1]).status_code == 200


def test_an_expired_code_is_refused(client, account, outbox, db_session):
    forgot(client)
    user = db_session.query(User).one()
    with pytest.raises(AccountError, match="invalid or has expired"):
        accounts.reset_password(db_session, user, reset_codes(outbox)[0], "new-password-2", now=utcnow() + timedelta(minutes=16))
    accounts.reset_password(db_session, user, reset_codes(outbox)[0], "new-password-2", now=utcnow() + timedelta(minutes=14))


def test_every_failure_says_the_same_thing_so_nothing_leaks(client, account, outbox):
    forgot(client)
    wrong_code = reset(client, "000000")
    unknown_account = reset(client, "000000", email="ghost@campus.edu")
    assert wrong_code.status_code == unknown_account.status_code == 422
    assert wrong_code.json() == unknown_account.json()


def test_a_verification_code_cannot_be_used_to_reset_a_password(client, outbox, monkeypatch):
    monkeypatch.setattr(settings, "auto_verify", False)
    register(client, email="asha@campus.edu", password="old-password-1")
    verify_code = [c for k, _, c in outbox if k == "verify"][0]
    forgot(client)
    assert reset(client, verify_code).status_code == 422  # a different purpose: it can't be replayed


def test_a_short_password_or_a_malformed_code_is_a_validation_error(client, account, outbox):
    forgot(client)
    code = reset_codes(outbox)[0]
    assert reset(client, code, new="short").status_code == 422
    assert reset(client, "12345").status_code == 422
    assert reset(client, "abcdef").status_code == 422
    assert reset(client, code).status_code == 200  # none of that used up the code


def test_resetting_also_verifies_an_unverified_account(client, outbox, monkeypatch, db_session):
    monkeypatch.setattr(settings, "auto_verify", False)
    register(client, email="asha@campus.edu", password="old-password-1")
    assert db_session.query(User).one().is_verified is False
    forgot(client)
    reset(client, reset_codes(outbox)[0])
    db_session.expire_all()
    assert db_session.query(User).one().is_verified is True  # they proved they control the inbox


def test_guessing_codes_is_rate_limited_per_address(client, account, outbox, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    limiter.reset()
    codes = [reset(client, "000000").status_code for _ in range(12)]
    assert 429 in codes[10:] and codes[0] == 422
