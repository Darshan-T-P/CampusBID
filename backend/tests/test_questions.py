from datetime import datetime, timedelta, timezone

from app.models import Category, Condition, Listing, ListingStatus, Notification
from tests.conftest import auth_header


def _make_listing(db_session, seller_id, title="Road Bike"):
    l = Listing(
        seller_id=seller_id,
        title=title,
        category=Category.cycle,
        condition=Condition.good,
        starting_price=1000,
        closes_at=datetime.now(timezone.utc) + timedelta(days=2),
        status=ListingStatus.active,
    )
    db_session.add(l)
    db_session.commit()
    return l


def test_list_questions_empty(client, db_session):
    seller_h = auth_header(client, email="seller1@campus.edu", name="Seller One")
    seller_id = int(client.get("/me", headers=seller_h).json()["id"])
    listing = _make_listing(db_session, seller_id)

    res = client.get(f"/listings/{listing.id}/questions")
    assert res.status_code == 200
    assert res.json() == []


def test_ask_question_and_answer_workflow(client, db_session):
    seller_h = auth_header(client, email="seller2@campus.edu", name="Seller Two")
    buyer_h = auth_header(client, email="buyer2@campus.edu", name="Buyer Two")

    seller_id = int(client.get("/me", headers=seller_h).json()["id"])
    buyer_id = int(client.get("/me", headers=buyer_h).json()["id"])
    listing = _make_listing(db_session, seller_id, "Hero Sprint")

    # 1. Buyer asks a question
    res = client.post(
        f"/listings/{listing.id}/questions",
        json={"question_text": "Do the disc brakes work smoothly?"},
        headers=buyer_h,
    )
    assert res.status_code == 201
    q = res.json()
    assert q["question_text"] == "Do the disc brakes work smoothly?"
    assert q["asker_name"] == "Buyer Two"
    assert q["answer_text"] is None
    q_id = q["id"]

    # Notification sent to seller
    notif = db_session.query(Notification).filter_by(user_id=seller_id, type="question").first()
    assert notif is not None
    assert "New question on Hero Sprint" in notif.title

    # 2. Seller replies to the question
    ans_res = client.post(
        f"/listings/{listing.id}/questions/{q_id}/answer",
        json={"answer_text": "Yes, replaced the brake pads last month. Both work perfectly!"},
        headers=seller_h,
    )
    assert ans_res.status_code == 200
    ans_data = ans_res.json()
    assert ans_data["answer_text"] == "Yes, replaced the brake pads last month. Both work perfectly!"
    assert ans_data["answered_at"] is not None

    # Notification sent to buyer
    buyer_notif = db_session.query(Notification).filter_by(user_id=buyer_id, type="answer").first()
    assert buyer_notif is not None
    assert "Seller answered your question" in buyer_notif.title

    # 3. Public get questions shows question and answer
    pub_res = client.get(f"/listings/{listing.id}/questions")
    assert pub_res.status_code == 200
    questions = pub_res.json()
    assert len(questions) == 1
    assert questions[0]["answer_text"] == "Yes, replaced the brake pads last month. Both work perfectly!"


def test_cannot_ask_question_on_own_listing(client, db_session):
    seller_h = auth_header(client, email="seller3@campus.edu", name="Seller Three")
    seller_id = int(client.get("/me", headers=seller_h).json()["id"])
    listing = _make_listing(db_session, seller_id)

    res = client.post(
        f"/listings/{listing.id}/questions",
        json={"question_text": "Self question?"},
        headers=seller_h,
    )
    assert res.status_code == 403


def test_non_seller_cannot_answer(client, db_session):
    seller_h = auth_header(client, email="seller4@campus.edu", name="Seller Four")
    buyer_h = auth_header(client, email="buyer4@campus.edu", name="Buyer Four")
    other_h = auth_header(client, email="other4@campus.edu", name="Other Student")

    seller_id = int(client.get("/me", headers=seller_h).json()["id"])
    listing = _make_listing(db_session, seller_id)

    # Buyer asks
    q_res = client.post(
        f"/listings/{listing.id}/questions",
        json={"question_text": "Is battery included?"},
        headers=buyer_h,
    )
    assert q_res.status_code == 201
    q_id = q_res.json()["id"]

    # Random student tries to answer
    res = client.post(
        f"/listings/{listing.id}/questions/{q_id}/answer",
        json={"answer_text": "I am not the seller"},
        headers=other_h,
    )
    assert res.status_code == 403
