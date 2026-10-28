from pydantic import BaseModel, Field, field_validator

from app.core.phone import clean_phone


class ProfileUpdate(BaseModel):
    """Fields a person may change about themselves. Anything left out stays as it is."""

    display_name: str | None = Field(default=None, max_length=80)
    department: str | None = Field(default=None, max_length=80)
    year_of_study: int | None = Field(default=None, ge=1, le=6)
    phone: str | None = Field(default=None, max_length=30)  # blank removes it

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, value: str | None) -> str | None:
        return clean_phone(value)

    @field_validator("display_name")
    @classmethod
    def name_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Display name cannot be empty")
        return value


class PasswordCheck(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)


class AccountDelete(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class SellingSummary(BaseModel):
    total: int  # every listing I have ever created
    open: int  # still accepting bids
    awaiting_decision: int  # ended with a winner; I must approve or reject
    awaiting_handover: int  # approved; waiting for the meet-up
    sold: int  # handover confirmed
    unsold: int  # ended with no bids
    other: int  # cancelled, rejected or failed pickup
    earned: int  # rupees from completed sales


class BuyingSummary(BaseModel):
    auctions: int  # distinct auctions I have bid on
    open: int  # of those, still running
    leading: int  # running auctions where I hold the top bid
    outbid: int  # running auctions where I do not
    won: int  # ended in my favour (provisional, reserved or completed)
    spent: int  # rupees on completed purchases
    bids_placed: int  # individual bids, including automatic ones
    automatic_maximums: int  # standing maximums on running auctions


class ProfileSummary(BaseModel):
    selling: SellingSummary
    buying: BuyingSummary
    unread_notifications: int
