from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.events import broadcaster
from app.models.listing import Listing, ListingStatus
from app.models.question import ListingQuestion
from app.models.user import User
from app.schemas.question import QuestionPublic
from app.services.notifications import notify


class QuestionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def to_public(q: ListingQuestion) -> QuestionPublic:
    return QuestionPublic(
        id=q.id,
        listing_id=q.listing_id,
        asker_id=q.asker_id,
        asker_name=q.asker.display_name if q.asker else "Student",
        asker_department=q.asker.department if q.asker else None,
        asker_year=q.asker.year_of_study if q.asker else None,
        question_text=q.question_text,
        answer_text=q.answer_text,
        created_at=q.created_at,
        answered_at=q.answered_at,
    )


def list_questions(db: Session, listing_id: int) -> list[QuestionPublic]:
    stmt = (
        select(ListingQuestion)
        .where(ListingQuestion.listing_id == listing_id)
        .order_by(ListingQuestion.created_at.desc())
    )
    rows = db.scalars(stmt).all()
    return [to_public(r) for r in rows]


def ask_question(db: Session, listing_id: int, user: User, text: str) -> QuestionPublic:
    listing = db.get(Listing, listing_id)
    if listing is None:
        raise QuestionError("not_found", "Listing not found")
    if listing.seller_id == user.id:
        raise QuestionError("own_listing", "You cannot ask a question on your own listing")
    if listing.status != ListingStatus.active:
        raise QuestionError("closed", "Questions can only be asked on active auctions")

    cleaned = text.strip()
    if len(cleaned) < 4:
        raise QuestionError("too_short", "Question must be at least 4 characters long")

    question = ListingQuestion(
        listing_id=listing_id,
        asker_id=user.id,
        question_text=cleaned,
        created_at=utcnow(),
    )
    db.add(question)

    # Notify the seller
    notify(
        db,
        listing.seller_id,
        "question",
        f"New question on {listing.title}",
        f"{user.display_name} asked: \"{cleaned[:80]}{'...' if len(cleaned) > 80 else ''}\"",
        listing.id,
        actor_id=user.id,
        now=question.created_at,
    )

    db.commit()
    db.refresh(question)
    pub = to_public(question)

    # Real-time SSE push to everyone on the page
    broadcaster.publish_nowait(
        "question_asked",
        {"listing_id": listing_id, "question": pub.model_dump(mode="json")},
        listing_id=listing_id,
    )

    return pub


def answer_question(db: Session, listing_id: int, question_id: int, user: User, text: str) -> QuestionPublic:
    listing = db.get(Listing, listing_id)
    if listing is None:
        raise QuestionError("not_found", "Listing not found")
    if listing.seller_id != user.id:
        raise QuestionError("not_seller", "Only the seller can answer questions on this listing")

    question = db.get(ListingQuestion, question_id)
    if question is None or question.listing_id != listing_id:
        raise QuestionError("not_found", "Question not found on this listing")

    cleaned = text.strip()
    if len(cleaned) < 2:
        raise QuestionError("too_short", "Answer must be at least 2 characters long")

    now = utcnow()
    question.answer_text = cleaned
    question.answered_at = now

    # Notify the student who asked
    notify(
        db,
        question.asker_id,
        "answer",
        f"Seller answered your question on {listing.title}",
        f"{user.display_name} replied: \"{cleaned[:80]}{'...' if len(cleaned) > 80 else ''}\"",
        listing.id,
        actor_id=user.id,
        now=now,
    )

    db.commit()
    db.refresh(question)
    pub = to_public(question)

    # Real-time SSE push
    broadcaster.publish_nowait(
        "question_answered",
        {"listing_id": listing_id, "question": pub.model_dump(mode="json")},
        listing_id=listing_id,
    )

    return pub
