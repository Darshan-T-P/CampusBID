"""Emails about how an auction and its sale turn out: queued with the event, delivered later, never twice."""

import email as email_lib
from datetime import timedelta
from email import policy

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.clock import utcnow
from app.core.config import settings
from app.models import Listing, OutboxEmail, User
from app.services import mailer, outbox
from app.services.auction import close_due_listings, ensure_closed
from app.services.closer import send_emails_once, sweep_once
from tests.conftest import auth_header, register
from tests.test_email import mail_server  # noqa: F401  (a real local SMTP server fixture)
from tests.test_listings import create


@pytest.fixture()
def sam(client):
    return auth_header(client, email="seller@campus.edu", name="Sam")


@pytest.fixture()
def alice(client):
    return auth_header(client, email="alice@campus.edu", name="Alice")


@pytest.fixture()
def bob(client):
    return auth_header(client, email="bob@campus.edu", name="Bob")


def give_phone(client, headers, number):
    assert client.patch("/me", json={"phone": number}, headers=headers).status_code == 200


def sold_listing(client, db, sam, alice, bob, spot="Library Gate"):
    """Alice wins at 550 (Bob was outbid); the auction has closed but nothing is approved yet."""
    lid = create(client, sam, handover_spot=spot).json()["id"]
    client.post(f"/listings/{lid}/bids", json={"amount": 500}, headers=bob)
    client.post(f"/listings/{lid}/bids", json={"amount": 550}, headers=alice)
    db.get(Listing, lid).closes_at = utcnow() - timedelta(seconds=1)
    db.commit()
    close_due_listings(db)
    return lid


def queued(db):
    return {(m.to_email, m.subject): m for m in db.query(OutboxEmail).all()}


def by_recipient(db):
    return {m.to_email: m for m in db.query(OutboxEmail).all()}


# --- when the auction closes -------------------------------------------------------------------------


def test_closing_emails_the_winner_and_the_seller_and_nobody_else(client, db_session, sam, alice, bob):
    sold_listing(client, db_session, sam, alice, bob)
    mails = by_recipient(db_session)
    assert set(mails) == {"alice@campus.edu", "seller@campus.edu"}  # not Bob (outbid), not watchers
    win = mails["alice@campus.edu"]
    assert win.subject == "You won Hero cycle for ₹550"
    assert "₹550" in win.body_text and "Library Gate" in win.body_text and "provisional" in win.body_text
    assert "Sam" in win.body_text and f"{settings.public_url}/listings/1" in win.body_text
    seller = mails["seller@campus.edu"]
    assert "Alice" in seller.body_text and "approve or reject" in seller.subject.lower()


def test_the_winners_email_does_not_contain_any_phone_number_before_approval(client, db_session, sam, alice, bob):
    give_phone(client, sam, "98765 43210")
    give_phone(client, alice, "91234 56789")
    sold_listing(client, db_session, sam, alice, bob)
    for m in db_session.query(OutboxEmail).all():
        assert "9876543210" not in m.body_text and "9123456789" not in m.body_text and "+91" not in m.body_text


def test_an_auction_with_no_bids_sends_no_email(client, db_session, sam):
    lid = create(client, sam).json()["id"]
    db_session.get(Listing, lid).closes_at = utcnow() - timedelta(seconds=1)
    db_session.commit()
    close_due_listings(db_session)
    assert db_session.query(OutboxEmail).count() == 0


def test_closing_through_a_page_view_or_the_sweep_sends_exactly_one_set(client, db_session, sam, alice, bob):
    lid = create(client, sam).json()["id"]
    client.post(f"/listings/{lid}/bids", json={"amount": 500}, headers=alice)
    db_session.get(Listing, lid).closes_at = utcnow() - timedelta(seconds=1)
    db_session.commit()
    ensure_closed(db_session, db_session.get(Listing, lid))  # someone opened the page first
    client.get(f"/listings/{lid}")
    sweep_once(lambda: sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)())  # then the sweep ran
    assert db_session.query(OutboxEmail).count() == 2


# --- when the seller approves or rejects ----------------------------------------------------------------


def test_approving_emails_each_side_the_others_contact_details(client, db_session, sam, alice, bob):
    give_phone(client, sam, "98765 43210")
    give_phone(client, alice, "91234 56789")
    lid = sold_listing(client, db_session, sam, alice, bob)
    db_session.query(OutboxEmail).delete()
    db_session.commit()
    assert client.post(f"/listings/{lid}/approve", headers=sam).status_code == 200
    mails = by_recipient(db_session)
    assert set(mails) == {"alice@campus.edu", "seller@campus.edu"}
    to_buyer, to_seller = mails["alice@campus.edu"], mails["seller@campus.edu"]
    assert to_buyer.subject == "Sale approved: Hero cycle" and "Sam" in to_buyer.body_text and "+919876543210" in to_buyer.body_text
    assert "Library Gate" in to_buyer.body_text and "public campus spot" in to_buyer.body_text
    assert to_seller.subject == "Contact details for Hero cycle" and "Alice" in to_seller.body_text and "+919123456789" in to_seller.body_text
    assert "+919123456789" not in to_buyer.body_text and "+919876543210" not in to_seller.body_text  # each only gets the other's


def test_a_missing_number_is_said_plainly_not_invented(client, db_session, sam, alice, bob):
    lid = sold_listing(client, db_session, sam, alice, bob)
    client.post(f"/listings/{lid}/approve", headers=sam)
    buyer_mail = [m for m in db_session.query(OutboxEmail).all() if m.subject.startswith("Sale approved")][0]
    assert "hasn't added a mobile number" in buyer_mail.body_text and "+91" not in buyer_mail.body_text


def test_rejecting_emails_only_the_winner(client, db_session, sam, alice, bob):
    lid = sold_listing(client, db_session, sam, alice, bob)
    db_session.query(OutboxEmail).delete()
    db_session.commit()
    client.post(f"/listings/{lid}/reject", json={"reason": "Changed my mind"}, headers=sam)
    [mail] = db_session.query(OutboxEmail).all()
    assert mail.to_email == "alice@campus.edu" and "did not go ahead" in mail.subject and "Changed my mind" in mail.body_text


def test_the_handover_and_pickup_steps_send_no_email(client, db_session, sam, alice, bob):
    lid = sold_listing(client, db_session, sam, alice, bob)
    client.post(f"/listings/{lid}/approve", headers=sam)
    before = db_session.query(OutboxEmail).count()
    client.post(f"/listings/{lid}/handover", headers=sam)
    assert db_session.query(OutboxEmail).count() == before


# --- opting out and who counts as a recipient --------------------------------------------------------------


def test_a_student_can_turn_these_emails_off_and_on(client, db_session, sam, alice, bob):
    assert client.get("/me", headers=alice).json()["notify_by_email"] is True
    assert client.patch("/me", json={"notify_by_email": False}, headers=alice).json()["notify_by_email"] is False
    sold_listing(client, db_session, sam, alice, bob)
    assert set(by_recipient(db_session)) == {"seller@campus.edu"}  # Alice opted out; the seller still hears
    assert client.patch("/me", json={"notify_by_email": True}, headers=alice).json()["notify_by_email"] is True
    assert client.patch("/me", json={"display_name": "Alice K"}, headers=alice).json()["notify_by_email"] is True  # untouched by other edits


def test_deleted_accounts_are_never_emailed(db_session):
    ghost = User(email="deleted-5@deleted.invalid", password_hash="!", display_name="Deleted user", is_verified=False)
    assert outbox.queue_email(db_session, ghost, mailer.sale_rejected_email("X", "No.", "http://x")) is None
    assert outbox.queue_email(db_session, None, mailer.sale_rejected_email("X", "No.", "http://x")) is None


# --- delivery ----------------------------------------------------------------------------------------------


class FakeSender:
    def __init__(self):
        self.sent, self.fail = [], False

    def __call__(self, to, subject, text, html=None):
        if self.fail:
            raise mailer.EmailError("mail server down")
        self.sent.append((to, subject))


@pytest.fixture()
def sender(monkeypatch):
    fake = FakeSender()
    monkeypatch.setattr(mailer, "send_email", fake)
    return fake


def factory(db):
    return lambda: sessionmaker(bind=db.get_bind(), expire_on_commit=False)()


def test_waiting_emails_are_sent_once_and_marked(client, db_session, sam, alice, bob, sender):
    sold_listing(client, db_session, sam, alice, bob)
    assert send_emails_once(factory(db_session)) == (2, 0)
    assert sorted(to for to, _ in sender.sent) == ["alice@campus.edu", "seller@campus.edu"]
    assert send_emails_once(factory(db_session)) == (0, 0)  # nothing left, nothing repeated
    assert len(sender.sent) == 2 and db_session.query(OutboxEmail).filter(OutboxEmail.sent_at.is_(None)).count() == 0


def test_a_down_mail_server_means_retry_later_with_a_growing_delay(client, db_session, sam, alice, bob, sender):
    sold_listing(client, db_session, sam, alice, bob)
    sender.fail = True
    now = utcnow()
    assert outbox.send_pending(db_session, now) == (0, 2)
    row = db_session.query(OutboxEmail).first()
    assert row.attempts == 1 and "mail server down" in row.last_error and row.next_try_at > now
    assert outbox.send_pending(db_session, now + timedelta(seconds=30)) == (0, 0)  # too soon
    sender.fail = False
    assert outbox.send_pending(db_session, now + timedelta(minutes=3)) == (2, 0)  # the server is back: delivered


def test_it_gives_up_after_five_tries(client, db_session, sam, alice, bob, sender):
    sold_listing(client, db_session, sam, alice, bob)
    sender.fail = True
    when = utcnow()
    for _ in range(outbox.MAX_ATTEMPTS + 2):
        when += timedelta(hours=1)
        outbox.send_pending(db_session, when)
    assert {m.attempts for m in db_session.query(OutboxEmail).all()} == {outbox.MAX_ATTEMPTS}
    assert not outbox.has_pending(db_session, when + timedelta(days=1))


def test_a_bad_address_is_not_retried(db_session, monkeypatch):
    monkeypatch.setattr(mailer, "send_email", lambda *a, **k: (_ for _ in ()).throw(ValueError("bad header")))
    db_session.add(OutboxEmail(to_email="x@campus.edu", subject="s", body_text="b"))
    db_session.commit()
    assert outbox.send_pending(db_session) == (0, 1)
    assert db_session.query(OutboxEmail).one().attempts == outbox.MAX_ATTEMPTS


def test_the_event_and_its_email_commit_together(client, db_session, sam, alice, bob):
    lid = create(client, sam).json()["id"]
    client.post(f"/listings/{lid}/bids", json={"amount": 500}, headers=alice)
    db_session.get(Listing, lid).closes_at = utcnow() - timedelta(seconds=1)
    db_session.commit()
    close_due_listings(db_session)
    db_session.expire_all()
    assert db_session.get(Listing, lid).status.value == "pending_approval" and db_session.query(OutboxEmail).count() == 2


def test_a_real_message_arrives_over_smtp_with_both_text_and_html(client, db_session, sam, alice, bob, mail_server):  # noqa: F811
    give_phone(client, sam, "98765 43210")
    lid = sold_listing(client, db_session, sam, alice, bob)
    client.post(f"/listings/{lid}/approve", headers=sam)
    sent, failed = send_emails_once(factory(db_session))
    assert (sent, failed) == (4, 0) and len(mail_server.envelopes) == 4
    to_alice = [e for e in mail_server.envelopes if e.rcpt_tos == ["alice@campus.edu"] and b"Sale approved" in e.content][0]
    msg = email_lib.message_from_bytes(to_alice.content, policy=policy.default)
    assert msg["Subject"] == "Sale approved: Hero cycle"
    assert "+919876543210" in msg.get_body(preferencelist=("plain",)).get_content()
    html_part = msg.get_body(preferencelist=("html",)).get_content()
    assert "Open the listing" in html_part and "<script" not in html_part
