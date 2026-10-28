from datetime import datetime

from sqlalchemy import func, select
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
        hidden=q.hidden,
        pinned=q.pinned,
    )


MAX_PINNED = 3


def list_questions(db: Session, listing_id: int, viewer: User | None = None) -> list[QuestionPublic]:
    """The thread, pinned answers first then newest. Hidden questions are only ever returned to the seller."""
    listing = db.get(Listing, listing_id)
    is_seller = viewer is not None and listing is not None and listing.seller_id == viewer.id
    stmt = select(ListingQuestion).where(ListingQuestion.listing_id == listing_id)
    if not is_seller:
        stmt = stmt.where(ListingQuestion.hidden.is_(False))
    rows = db.scalars(stmt.order_by(ListingQuestion.pinned.desc(), ListingQuestion.created_at.desc())).all()
    return [to_public(r) for r in rows]


def _seller_question(db: Session, listing_id: int, question_id: int, user: User) -> ListingQuestion:
    listing = db.get(Listing, listing_id)
    if listing is None:
        raise QuestionError("not_found", "Listing not found")
    if listing.seller_id != user.id:
        raise QuestionError("not_seller", "Only the seller can moderate questions on this listing")
    question = db.get(ListingQuestion, question_id)
    if question is None or question.listing_id != listing_id:
        raise QuestionError("not_found", "Question not found on this listing")
    return question


def set_hidden(db: Session, listing_id: int, question_id: int, user: User, hidden: bool) -> QuestionPublic:
    """Seller hides spam from everyone else (and can bring it back). Hiding also unpins it."""
    question = _seller_question(db, listing_id, question_id, user)
    question.hidden = hidden
    if hidden:
        question.pinned = False
    db.commit()
    db.refresh(question)
    # No content in the event: a hidden question must not leak. Viewers just re-read the thread.
    broadcaster.publish_nowait("question_updated", {"listing_id": listing_id}, listing_id=listing_id)
    return to_public(question)


def set_pinned(db: Session, listing_id: int, question_id: int, user: User, pinned: bool) -> QuestionPublic:
    """Seller pins a helpful answered question to the top (up to three)."""
    question = _seller_question(db, listing_id, question_id, user)
    if pinned:
        if not question.answer_text:
            raise QuestionError("not_answered", "Answer the question before pinning it")
        if question.hidden:
            raise QuestionError("hidden", "Unhide the question before pinning it")
        already = db.scalar(
            select(func.count()).select_from(ListingQuestion).where(
                ListingQuestion.listing_id == listing_id, ListingQuestion.pinned.is_(True), ListingQuestion.id != question_id
            )
        )
        if already >= MAX_PINNED:
            raise QuestionError("limit", f"You can pin up to {MAX_PINNED} questions. Unpin one first.")
    question.pinned = pinned
    db.commit()
    db.refresh(question)
    broadcaster.publish_nowait("question_updated", {"listing_id": listing_id}, listing_id=listing_id)
    return to_public(question)


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
