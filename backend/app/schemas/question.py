from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class QuestionCreate(BaseModel):
    question_text: str = Field(..., min_length=4, max_length=500, description="The condition or detail question")


class AnswerCreate(BaseModel):
    answer_text: str = Field(..., min_length=2, max_length=1000, description="The seller's public answer")


class QuestionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    listing_id: int
    asker_id: int
    asker_name: str
    asker_department: str | None = None
    asker_year: int | None = None
    question_text: str
    answer_text: str | None = None
    created_at: datetime
    answered_at: datetime | None = None
    hidden: bool = False  # only the seller ever receives hidden questions
    pinned: bool = False


class QuestionHide(BaseModel):
    hidden: bool = True


class QuestionPin(BaseModel):
    pinned: bool = True
