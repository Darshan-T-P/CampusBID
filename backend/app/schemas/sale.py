from pydantic import BaseModel, Field


class RejectRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class ContactInfo(BaseModel):
    """The other side of an approved sale. Seen only by the seller and the winner."""

    role: str  # what the other person is to you: "seller" or "buyer"
    name: str
    phone: str | None  # null when they haven't added a number
    listing_title: str
