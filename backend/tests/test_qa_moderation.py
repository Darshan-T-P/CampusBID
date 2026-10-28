"""Q&A moderation: the seller hides spam and pins helpful answers."""

import pytest

from app.core.events import broadcaster
from tests.conftest import auth_header
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


@pytest.fixture()
def lid(client, sam):
    return create(client, sam).json()["id"]


def ask(client, headers, lid, text="Do the gears shift well?"):
    r = client.post(f"/listings/{lid}/questions", json={"question_text": text}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def answer(client, headers, lid, qid, text="Yes, they are smooth."):
    assert client.post(f"/listings/{lid}/questions/{qid}/answer", json={"answer_text": text}, headers=headers).status_code == 200


def thread(client, lid, headers=None):
    return client.get(f"/listings/{lid}/questions", headers=headers or {}).json()


# --- hiding -------------------------------------------------------------------------------------------


def test_a_hidden_question_disappears_for_everyone_but_the_seller(client, sam, alice, bob, lid):
    spam = ask(client, alice, lid, "BUY CRYPTO NOW http://spam")
    ask(client, bob, lid, "Is the frame scratched?")
    assert client.post(f"/listings/{lid}/questions/{spam}/hide", headers=sam).status_code == 200
    assert [q["question_text"] for q in thread(client, lid)] == ["Is the frame scratched?"]  # a visitor
    assert [q["question_text"] for q in thread(client, lid, bob)] == ["Is the frame scratched?"]  # another student
    assert [q["question_text"] for q in thread(client, lid, alice)] == ["Is the frame scratched?"]  # even the asker
    seen = thread(client, lid, sam)  # the seller still sees it, flagged, so they can undo it
    assert len(seen) == 2 and [q["hidden"] for q in seen if q["question_text"].startswith("BUY")] == [True]


def test_the_seller_can_bring_a_question_back(client, sam, alice, lid):
    qid = ask(client, alice, lid)
    client.post(f"/listings/{lid}/questions/{qid}/hide", headers=sam)
    assert thread(client, lid) == []
    client.post(f"/listings/{lid}/questions/{qid}/hide", json={"hidden": False}, headers=sam)
    assert len(thread(client, lid)) == 1


def test_only_the_seller_can_moderate(client, sam, alice, bob, lid):
    qid = ask(client, alice, lid)
    for who in (alice, bob):
        assert client.post(f"/listings/{lid}/questions/{qid}/hide", headers=who).status_code == 403
        assert client.post(f"/listings/{lid}/questions/{qid}/pin", headers=who).status_code == 403
    assert client.post(f"/listings/{lid}/questions/{qid}/hide").status_code == 401
    assert len(thread(client, lid)) == 1


def test_a_question_from_another_listing_or_a_missing_one_is_not_found(client, sam, alice, lid):
    other = create(client, sam, title="Second").json()["id"]
    qid = ask(client, alice, lid)
    assert client.post(f"/listings/{other}/questions/{qid}/hide", headers=sam).status_code == 404
    assert client.post(f"/listings/{lid}/questions/999/hide", headers=sam).status_code == 404
    assert client.post("/listings/999/questions/1/hide", headers=sam).status_code == 404


def test_a_hidden_question_does_not_leak_through_the_live_event(client, sam, alice, lid):
    import asyncio

    loop = asyncio.new_event_loop()
    q = loop.run_until_complete(broadcaster.subscribe(lid))
    qid = ask(client, alice, lid, "secret spam text")
    loop.run_until_complete(asyncio.wait_for(q.get(), 2))  # the "asked" event
    client.post(f"/listings/{lid}/questions/{qid}/hide", headers=sam)
    event = loop.run_until_complete(asyncio.wait_for(q.get(), 2))
    loop.close()
    assert event["event"] == "question_updated" and "secret" not in str(event)


# --- pinning ----------------------------------------------------------------------------------------------


def test_pinned_answers_come_first(client, sam, alice, bob, lid):
    older = ask(client, alice, lid, "Is it the 21 gear model?")
    newer = ask(client, bob, lid, "Any rust on the chain?")
    answer(client, sam, lid, older)
    assert client.post(f"/listings/{lid}/questions/{older}/pin", headers=sam).json()["pinned"] is True
    assert [q["id"] for q in thread(client, lid)] == [older, newer]  # newest-first would have put `newer` on top
    client.post(f"/listings/{lid}/questions/{older}/pin", json={"pinned": False}, headers=sam)
    assert [q["id"] for q in thread(client, lid)] == [newer, older]


def test_only_an_answered_question_can_be_pinned(client, sam, alice, lid):
    qid = ask(client, alice, lid)
    r = client.post(f"/listings/{lid}/questions/{qid}/pin", headers=sam)
    assert r.status_code == 409 and "Answer the question" in r.json()["detail"]


def test_at_most_three_are_pinned(client, sam, alice, lid):
    ids = [ask(client, alice, lid, f"Question number {i}?") for i in range(4)]
    for i in ids:
        answer(client, sam, lid, i)
    assert [client.post(f"/listings/{lid}/questions/{i}/pin", headers=sam).status_code for i in ids] == [200, 200, 200, 409]


def test_hiding_unpins_and_a_hidden_question_cannot_be_pinned(client, sam, alice, lid):
    qid = ask(client, alice, lid)
    answer(client, sam, lid, qid)
    client.post(f"/listings/{lid}/questions/{qid}/pin", headers=sam)
    hidden = client.post(f"/listings/{lid}/questions/{qid}/hide", headers=sam).json()
    assert hidden["hidden"] is True and hidden["pinned"] is False
    assert client.post(f"/listings/{lid}/questions/{qid}/pin", headers=sam).status_code == 409


def test_a_bad_token_just_means_a_visitor(client, lid, alice):
    ask(client, alice, lid)
    assert len(client.get(f"/listings/{lid}/questions", headers={"Authorization": "Bearer nonsense"}).json()) == 1
