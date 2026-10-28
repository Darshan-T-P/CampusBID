from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import Category
from app.schemas.listing import MAX_PRICE


class WantCreate(BaseModel):
    keywords: str = Field(default="", max_length=80, description="Words to look for, e.g. 'cycle'")
    category: Category | None = None
    max_price: int | None = Field(default=None, ge=1, le=MAX_PRICE, description="Rupees; matches a starting price up to this")


class WantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    keywords: str
    category: Category | None
    max_price: int | None
    created_at: datetime
