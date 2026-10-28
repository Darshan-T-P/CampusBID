from datetime import datetime
from pydantic import BaseModel

from app.models.listing import Category, Condition


class FastMovingItem(BaseModel):
    id: int
    title: str
    category: Category
    condition: Condition
    starting_price: int
    current_price: int | None = None
    bid_count: int
    closes_at: datetime
    photo: str | None = None
    price_growth_pct: float = 0.0
    status: str
    is_hot: bool = False


class CategoryTrend(BaseModel):
    category: str
    label: str
    total_listings: int
    active_listings: int
    completed_sales: int
    total_bids: int
    avg_bids_per_item: float
    sell_through_rate: float
    avg_sale_price: int | None = None
    demand_badge: str


class StudentInterest(BaseModel):
    keyword: str
    category: str | None = None
    wants_count: int
    active_listings_count: int
    unfilled_demand: bool


class MarketPulse(BaseModel):
    total_active_listings: int
    total_completed_sales: int
    total_volume_traded: int
    total_bids_placed: int
    overall_sell_through_rate: float
    fast_moving: list[FastMovingItem]
    category_trends: list[CategoryTrend]
    student_interests: list[StudentInterest]
    recent_successful_sales: list[FastMovingItem]
