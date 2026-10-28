from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.models import Category, Condition
from app.schemas.pricing import PriceSuggestion
from app.services import pricing as service

router = APIRouter(prefix="/pricing", tags=["pricing"])


@router.get("/suggestion", response_model=PriceSuggestion)
def price_suggestion(
    category: Category,
    user: CurrentUser,
    db: DbSession,
    condition: Condition | None = None,
    title: Annotated[str | None, Query(max_length=120, description="Words from the title, to find similar items")] = None,
):
    """What similar items sold for recently, so a seller can pick a sensible starting price. Aggregates only."""
    return service.suggest(db, category, condition, title)
