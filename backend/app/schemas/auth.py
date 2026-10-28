from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=80)
    department: str | None = Field(default=None, max_length=80)
    year_of_study: int | None = Field(default=None, ge=1, le=6, description="1-5, or 6 for postgraduate")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    # False means the user must enter their emailed code before they can list or bid.
    is_verified: bool = False


class UserMe(BaseModel):
    """The caller's own profile. Email is only ever returned here, never in public views."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    display_name: str
    department: str | None = None
    year_of_study: int | None = None
    is_verified: bool
    created_at: datetime


class VerifyRequest(BaseModel):
    code: str = Field(pattern=r"^\d{6}$", description="The 6-digit code from your email")


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$", description="The 6-digit code from the email")
    new_password: str = Field(min_length=8, max_length=128)
