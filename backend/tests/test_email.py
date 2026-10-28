"""Sending email: message building, the console/SMTP backends, and what the routes send (and don't)."""

import email as email_lib
from email import policy
import logging
import smtplib
import socket
import time

import pytest
from aiosmtpd.controller import Controller

from app.core.config import settings
from app.services import accounts, mailer
from tests.conftest import register


# --- the message ------------------------------------------------------------


def test_a_message_has_the_right_headers_and_both_text_and_html():
    subject, text, page = mailer.verification_email("123456", 10)
    msg = mailer.build_message("asha@campus.edu", subject, text, page)
    assert msg["To"] == "asha@campus.edu" and msg["From"] == settings.email_from
    assert "123456" in msg["Subject"] and msg["Date"] and msg["Message-ID"]
    assert msg.is_multipart()
    parts = {p.get_content_type(): p.get_content() for p in msg.iter_parts()}
    assert set(parts) == {"text/plain", "text/html"}
    assert "123456" in parts["text/plain"] and "123456" in parts["text/html"]
    assert "10 minutes" in parts["text/plain"]


def test_each_message_says_what_it_is_for():
    assert "verification" in mailer.verification_email("111111", 10)[0].lower()
    reset_subject, reset_text, _ = mailer.password_reset_email("222222", 15)
    assert "reset" in reset_subject.lower() and "15 minutes" in reset_text and "ignore this email" in reset_text
    assert "changed" in mailer.password_changed_email()[0].lower()


def test_html_content_is_escaped():
    _, page = mailer._wrap("<script>alert(1)</script>", ["a < b & c"], code="123456")
    assert "<script>" not in page and "&lt;script&gt;" in page and "a &lt; b &amp; c" in page


def test_a_recipient_cannot_smuggle_extra_headers():
    with pytest.raises(ValueError):
        mailer.build_message("a@campus.edu\nBcc: victim@example.com", "subject", "body")


# --- the console backend ----------------------------------------------------


def test_console_backend_in_dev_mode_logs_the_code_so_you_can_copy_it(caplog, monkeypatch):
    monkeypatch.setattr(settings, "email_backend", "console")
    monkeypatch.setattr(settings, "dev_mode", True)
    with caplog.at_level(logging.WARNING, logger="campusbid.mail"):
        accounts.deliver_code("asha@campus.edu", "654321")
    assert "654321" in caplog.text and "asha@campus.edu" in caplog.text


def test_console_backend_outside_dev_mode_sends_nothing_and_never_logs_the_code(caplog, monkeypatch):
    monkeypatch.setattr(settings, "email_backend", "console")
    monkeypatch.setattr(settings, "dev_mode", False)
    monkeypatch.setattr(smtplib, "SMTP", lambda *a, **k: pytest.fail("must not touch the network"))
    with caplog.at_level(logging.WARNING, logger="campusbid.mail"):
        accounts.deliver_code("asha@campus.edu", "654321")
    assert "654321" not in caplog.text and "nothing was sent" in caplog.text


# --- SMTP: for real, over a local mail server --------------------------------


class Inbox:
    def __init__(self):
        self.envelopes = []

    async def handle_DATA(self, server, session, envelope):
        self.envelopes.append(envelope)
        return "250 Message accepted"


@pytest.fixture()
def mail_server(monkeypatch):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    inbox = Inbox()
    controller = Controller(inbox, hostname="127.0.0.1", port=port)
    controller.start()
    monkeypatch.setattr(settings, "email_backend", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "127.0.0.1")
    monkeypatch.setattr(settings, "smtp_port", port)
    monkeypatch.setattr(settings, "smtp_starttls", False)  # the throwaway server has no TLS
    monkeypatch.setattr(settings, "smtp_username", "")
    monkeypatch.setattr(settings, "email_from", "Relay <no-reply@relay.test>")
    yield inbox
    controller.stop()


def test_a_real_email_is_delivered_over_the_smtp_protocol(mail_server):
    accounts.deliver_code("asha@campus.edu", "246810")
    assert len(mail_server.envelopes) == 1
    envelope = mail_server.envelopes[0]
    assert envelope.rcpt_tos == ["asha@campus.edu"] and envelope.mail_from == "no-reply@relay.test"
    received = email_lib.message_from_bytes(envelope.content, policy=policy.default)
    assert "246810" in received["Subject"] and received["From"] == "Relay <no-reply@relay.test>"
    body = received.get_body(preferencelist=("plain",)).get_content()
    assert "246810" in body and "expires" in body


def test_each_kind_of_message_goes_out(mail_server):
    accounts.deliver_code("a@campus.edu", "111111")
    accounts.deliver_reset_code("a@campus.edu", "222222")
    accounts.deliver_password_changed("a@campus.edu")
    subjects = [email_lib.message_from_bytes(e.content, policy=policy.default)["Subject"] for e in mail_server.envelopes]
    assert any("verification" in s for s in subjects) and any("reset" in s for s in subjects) and any("changed" in s for s in subjects)


# --- SMTP: the conversation (TLS, login), with a recording stand-in ---------


class FakeSMTP:
    instances = []
    fail_login = False

    def __init__(self, host, port, timeout=None, context=None):
        self.calls = [("connect", host, port)]
        self.timeout = timeout
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.calls.append(("quit",))

    def ehlo(self):
        self.calls.append(("ehlo",))

    def starttls(self, context=None):
        self.calls.append(("starttls", context is not None))

    def login(self, user, password):
        if FakeSMTP.fail_login:
            raise smtplib.SMTPAuthenticationError(535, b"5.7.8 bad credentials")
        self.calls.append(("login", user))

    def send_message(self, msg):
        self.calls.append(("send", msg["To"]))


@pytest.fixture()
def fake_smtp(monkeypatch):
    FakeSMTP.instances, FakeSMTP.fail_login = [], False
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(settings, "email_backend", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_username", "apikey-user")
    monkeypatch.setattr(settings, "smtp_password", "s3cret-password")
    monkeypatch.setattr(settings, "smtp_starttls", True)
    monkeypatch.setattr(settings, "smtp_ssl", False)
    return FakeSMTP


def test_the_connection_upgrades_to_tls_before_logging_in(fake_smtp):
    mailer.send_email("a@campus.edu", "hi", "body")
    calls = [c[0] for c in fake_smtp.instances[0].calls]
    assert calls == ["connect", "ehlo", "starttls", "ehlo", "login", "send", "quit"]  # credentials never travel in clear
    assert fake_smtp.instances[0].timeout == settings.smtp_timeout  # a hung mail server can't hang us forever


def test_implicit_ssl_mode_skips_starttls(fake_smtp, monkeypatch):
    monkeypatch.setattr(settings, "smtp_ssl", True)
    monkeypatch.setattr(settings, "smtp_port", 465)
    mailer.send_email("a@campus.edu", "hi", "body")
    assert "starttls" not in [c[0] for c in fake_smtp.instances[0].calls]


def test_no_login_is_attempted_without_a_username(fake_smtp, monkeypatch):
    monkeypatch.setattr(settings, "smtp_username", "")
    mailer.send_email("a@campus.edu", "hi", "body")
    assert "login" not in [c[0] for c in fake_smtp.instances[0].calls]


def test_a_bad_password_gives_a_clear_error_that_never_contains_the_password(fake_smtp):
    fake_smtp.fail_login = True
    with pytest.raises(mailer.EmailError) as exc:
        mailer.send_email("a@campus.edu", "hi", "body")
    assert "username or password" in str(exc.value) and "535" in str(exc.value)
    assert "s3cret-password" not in str(exc.value)


def test_an_unreachable_server_is_reported_not_raised_as_a_raw_socket_error(monkeypatch):
    monkeypatch.setattr(settings, "email_backend", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "127.0.0.1")
    monkeypatch.setattr(settings, "smtp_port", 1)  # nothing listens here
    with pytest.raises(mailer.EmailError, match="Could not send"):
        mailer.send_email("a@campus.edu", "hi", "body")


def test_a_failed_send_never_crashes_the_request_and_never_logs_the_code(fake_smtp, caplog):
    fake_smtp.fail_login = True
    with caplog.at_level(logging.ERROR, logger="campusbid.accounts"):
        accounts.deliver_code("asha@campus.edu", "135790")  # must not raise
    assert "Could not email asha@campus.edu" in caplog.text
    assert "135790" not in caplog.text and "s3cret-password" not in caplog.text


# --- what the routes send ---------------------------------------------------


@pytest.fixture()
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(accounts, "deliver_code", lambda e, c: sent.append(("verify", e, c)))
    monkeypatch.setattr(accounts, "deliver_reset_code", lambda e, c: sent.append(("reset", e, c)))
    monkeypatch.setattr(accounts, "deliver_password_changed", lambda e: sent.append(("changed", e, None)))
    return sent


def test_registering_emails_one_verification_code_after_the_response(client, outbox, monkeypatch):
    monkeypatch.setattr(settings, "auto_verify", False)
    assert register(client, email="asha@campus.edu").status_code == 201
    assert [(kind, to) for kind, to, _ in outbox] == [("verify", "asha@campus.edu")]
    assert len(outbox[0][2]) == 6 and outbox[0][2].isdigit()


def test_auto_verified_accounts_get_no_email(client, outbox):
    register(client)  # the default test setup has auto_verify on
    assert outbox == []


def test_resending_emails_a_new_code(client, outbox, monkeypatch):
    monkeypatch.setattr(settings, "auto_verify", False)
    monkeypatch.setattr(settings, "verification_resend_cooldown_seconds", 0)
    token = register(client).json()["access_token"]
    assert client.post("/auth/resend-code", headers={"Authorization": f"Bearer {token}"}).status_code == 204
    assert [k for k, *_ in outbox] == ["verify", "verify"]


def test_changing_the_password_emails_a_notice(client, outbox):
    token = register(client).json()["access_token"]
    r = client.post("/me/password", json={"current_password": "password123", "new_password": "a-better-password"}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and outbox == [("changed", "a@campus.edu", None)]


# --- starting up -------------------------------------------------------------


def test_a_deployment_without_email_refuses_to_start(monkeypatch):
    from app.main import check_startup_settings

    monkeypatch.setattr(settings, "dev_mode", False)
    monkeypatch.setattr(settings, "auto_verify", False)
    monkeypatch.setattr(settings, "allowed_email_domains", "college.edu")
    monkeypatch.setattr(settings, "secret_key", "k" * 40)
    monkeypatch.setattr(settings, "email_backend", "console")
    with pytest.raises(RuntimeError, match="Email is not configured"):
        check_startup_settings()

    monkeypatch.setattr(settings, "email_backend", "smtp")
    with pytest.raises(RuntimeError, match="Email is not configured"):  # smtp chosen, but no host
        check_startup_settings()
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    check_startup_settings()  # fine once a host and sender are set

    monkeypatch.setattr(settings, "email_backend", "console")
    monkeypatch.setattr(settings, "auto_verify", True)
    check_startup_settings()  # fine: demo mode needs no email
