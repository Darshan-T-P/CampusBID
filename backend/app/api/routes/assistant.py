from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.ratelimit import enforce
from app.schemas.assistant import AssistantStatus, ChatRequest, ChatResponse
from app.services import assistant as service

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.get("/status", response_model=AssistantStatus)
def status() -> AssistantStatus:
    """Whether this server has the assistant switched on (it needs a GROQ_API_KEY)."""
    return AssistantStatus(enabled=settings.assistant_ready)


@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, user: CurrentUser, db: DbSession):
    """Ask the assistant. It can search, look at listings and prepare an automatic bid for the student to confirm,
    and it can do nothing else. Nothing is bid unless the student confirms in the app."""
    if not settings.assistant_ready:
        raise HTTPException(503, "The assistant isn't set up on this server.")
    if body.messages[-1].role != "user":
        raise HTTPException(422, "The last message must be the student's")
    enforce(f"assistant:user:{user.id}", limit=20, window=600)
    enforce("assistant:all", limit=120, window=600)  # one shared model quota: keep a single student from using it all
    try:
        reply = service.answer(db, user, body.messages)
    except service.AssistantError as e:
        raise HTTPException(e.status, e.message) from e
    return ChatResponse(reply=reply.text, listings=reply.cards, proposals=reply.proposals)
