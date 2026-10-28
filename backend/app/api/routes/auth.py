from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.ratelimit import enforce
from app.core.security import (
    burn_password_check,
    create_access_token,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.models import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserMe, VerifyRequest
from app.services import accounts
from app.services.errors import AccountError

router = APIRouter(tags=["auth"])

_HTTP_STATUS = {
    "invalid": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "conflict": status.HTTP_409_CONFLICT,
    "forbidden": status.HTTP_403_FORBIDDEN,
    "rate_limited": status.HTTP_429_TOO_MANY_REQUESTS,
}


def _http_error(e: AccountError) -> HTTPException:
    return HTTPException(_HTTP_STATUS[e.code], e.message)


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, request: Request, db: DbSession):
    enforce(f"register:ip:{_ip(request)}", limit=10, window=3600)
    try:
        email = accounts.check_registration_email(body.email)
    except AccountError as e:
        raise _http_error(e) from e
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = User(
        email=email,
        password_hash=hash_password(body.password),
        display_name=body.display_name.strip(),
        is_verified=settings.auto_verify,
    )
    db.add(user)
    db.commit()
    if not user.is_verified:
        accounts.issue_code(db, user)
    return TokenResponse(access_token=create_access_token(user.id), is_verified=user.is_verified)


@router.post("/auth/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: DbSession):
    try:
        email = accounts.normalize_email(body.email)
    except AccountError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password") from None
    enforce(f"login:ip:{_ip(request)}", limit=50, window=600)
    enforce(f"login:email:{email}", limit=10, window=600)  # slows password guessing on one account
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        burn_password_check(body.password)  # same cost as a real check: timing must not reveal who has an account
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)  # quietly move old accounts to the stronger settings
        db.commit()
    return TokenResponse(access_token=create_access_token(user.id), is_verified=user.is_verified)


@router.post("/auth/verify", response_model=UserMe)
def verify_email(body: VerifyRequest, user: CurrentUser, db: DbSession):
    enforce(f"verify:user:{user.id}", limit=15, window=600)
    try:
        accounts.verify_code(db, user, body.code)
    except AccountError as e:
        raise _http_error(e) from e
    return user


@router.post("/auth/resend-code", status_code=status.HTTP_204_NO_CONTENT)
def resend_code(user: CurrentUser, db: DbSession):
    if user.is_verified:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already verified")
    enforce(f"resend:user:{user.id}", limit=5, window=3600)
    try:
        accounts.issue_code(db, user)
    except AccountError as e:
        raise _http_error(e) from e


@router.get("/me", response_model=UserMe)
def me(user: CurrentUser):
    return user
