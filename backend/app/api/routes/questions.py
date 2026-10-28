from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbSession, OptionalUser, VerifiedUser
from app.core.ratelimit import enforce
from app.schemas.question import AnswerCreate, QuestionCreate, QuestionHide, QuestionPin, QuestionPublic
from app.services import questions as question_service
from app.services.questions import QuestionError

router = APIRouter(tags=["questions"])

_HTTP_STATUS = {
    "not_found": status.HTTP_404_NOT_FOUND,
    "own_listing": status.HTTP_403_FORBIDDEN,
    "not_seller": status.HTTP_403_FORBIDDEN,
    "closed": status.HTTP_409_CONFLICT,
    "too_short": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "not_answered": status.HTTP_409_CONFLICT,
    "hidden": status.HTTP_409_CONFLICT,
    "limit": status.HTTP_409_CONFLICT,
}


def _error(e: QuestionError) -> HTTPException:
    return HTTPException(_HTTP_STATUS.get(e.code, status.HTTP_400_BAD_REQUEST), e.message)


@router.get("/listings/{listing_id}/questions", response_model=list[QuestionPublic])
def get_questions(listing_id: int, db: DbSession, user: OptionalUser):
    """Public listing Q&A thread: pinned first, then newest. Hidden questions are sent only to the seller."""
    return question_service.list_questions(db, listing_id, user)


@router.post("/listings/{listing_id}/questions", response_model=QuestionPublic, status_code=status.HTTP_201_CREATED)
def post_question(listing_id: int, body: QuestionCreate, user: VerifiedUser, db: DbSession):
    """Ask a question about the item condition or details before bidding."""
    enforce(f"ask:user:{user.id}", limit=20, window=3600)
    try:
        return question_service.ask_question(db, listing_id, user, body.question_text)
    except QuestionError as e:
        raise _error(e) from e


@router.post("/listings/{listing_id}/questions/{question_id}/answer", response_model=QuestionPublic)
def post_answer(listing_id: int, question_id: int, body: AnswerCreate, user: VerifiedUser, db: DbSession):
    """Seller replies to a buyer's question publicly."""
    enforce(f"answer:user:{user.id}", limit=40, window=3600)
    try:
        return question_service.answer_question(db, listing_id, question_id, user, body.answer_text)
    except QuestionError as e:
        raise _error(e) from e


@router.post("/listings/{listing_id}/questions/{question_id}/hide", response_model=QuestionPublic)
def hide_question(listing_id: int, question_id: int, user: VerifiedUser, db: DbSession, body: QuestionHide | None = None):
    """Seller hides spam from everyone else (hidden=false brings it back)."""
    enforce(f"moderate:user:{user.id}", limit=120, window=3600)
    try:
        return question_service.set_hidden(db, listing_id, question_id, user, body.hidden if body else True)
    except QuestionError as e:
        raise _error(e) from e


@router.post("/listings/{listing_id}/questions/{question_id}/pin", response_model=QuestionPublic)
def pin_question(listing_id: int, question_id: int, user: VerifiedUser, db: DbSession, body: QuestionPin | None = None):
    """Seller pins a helpful answered question to the top of the thread (pinned=false unpins it)."""
    enforce(f"moderate:user:{user.id}", limit=120, window=3600)
    try:
        return question_service.set_pinned(db, listing_id, question_id, user, body.pinned if body else True)
    except QuestionError as e:
        raise _error(e) from e
