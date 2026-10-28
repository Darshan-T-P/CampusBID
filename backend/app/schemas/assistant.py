from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.listing import ListingCard

MAX_MESSAGE_CHARS = 800
MAX_MESSAGES = 12


class ChatMessage(BaseModel):
    # Only these two roles are accepted from a browser: it can never send system or tool messages.
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=MAX_MESSAGES)


class Proposal(BaseModel):
    """An automatic bid the assistant suggests. Nothing has happened: the student must confirm it."""

    listing_id: int
    title: str
    max_amount: int
    current_price: int | None
    min_next_bid: int
    closes_at: datetime
    thumbnail: str | None = None


class ChatResponse(BaseModel):
    reply: str
    listings: list[ListingCard] = []  # the auctions the answer is about, for showing as cards
    proposals: list[Proposal] = []  # to confirm or dismiss


class AssistantStatus(BaseModel):
    enabled: bool
