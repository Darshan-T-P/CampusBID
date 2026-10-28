from fastapi import APIRouter

from app.api.deps import DbSession
from app.schemas.analytics import MarketPulse
from app.services import analytics as service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/market-pulse", response_model=MarketPulse)
def get_market_pulse(db: DbSession):
    """Real-time market insights: fast-moving products, category demand, and student interests based on bids and sales."""
    return service.get_market_pulse(db)
