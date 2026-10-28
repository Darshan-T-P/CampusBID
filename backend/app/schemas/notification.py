from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    title: str
    body: str
    listing_id: int | None
    created_at: datetime
    read_at: datetime | None  # null = unread


class NotificationFeed(BaseModel):
    items: list[NotificationOut]
    unread_count: int  # all unread, not just this page: drives the bell badge
    latest_id: int | None  # highest id in `items`; pass it back as `since_id` to poll
    oldest_id: int | None = None  # lowest id in `items`; pass it back as `before_id` to load older ones


class MarkAllResult(BaseModel):
    marked: int
