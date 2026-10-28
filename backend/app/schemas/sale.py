from pydantic import BaseModel, Field


class RejectRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
