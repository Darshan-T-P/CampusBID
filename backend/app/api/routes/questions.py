from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbSession, VerifiedUser
from app.core.ratelimit import enforce
from app.schemas.question import AnswerCreate, QuestionCreate, QuestionPublic
from app.services import questions as question_service
from app.services.questions import QuestionError

router = APIRouter(tags=["questions"])

_HTTP_STATUS = {
    "not_found": status.HTTP_404_NOT_FOUND,
    "own_listing": status.HTTP_403_FORBIDDEN,
    "not_seller": status.HTTP_403_FORBIDDEN,
    "closed": status.HTTP_409_CONFLICT,
    "too_short": status.HTTP_422_UNPROCESSABLE_CONTENT,
}


def _error(e: QuestionError) -> HTTPException:
    return HTTPException(_HTTP_STATUS.get(e.code, status.HTTP_400_BAD_REQUEST), e.message)


@router.get("/listings/{listing_id}/questions", response_model=list[QuestionPublic])
def get_questions(listing_id: int, db: DbSession):
    """Public listing Q&A thread: any student can read questions and seller answers."""
    return question_service.list_questions(db, listing_id)


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
