from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
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
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserMe,
    VerifyRequest,
)
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
def register(body: RegisterRequest, request: Request, background: BackgroundTasks, db: DbSession):
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
        department=(body.department or "").strip() or None,
        year_of_study=body.year_of_study,
        is_verified=settings.auto_verify,
    )
    db.add(user)
    db.commit()
    if not user.is_verified:
        code = accounts.issue_code(db, user)
        background.add_task(accounts.deliver_code, user.email, code)  # after the response: sending can take seconds
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
def resend_code(user: CurrentUser, background: BackgroundTasks, db: DbSession):
    if user.is_verified:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already verified")
    enforce(f"resend:user:{user.id}", limit=5, window=3600)
    try:
        code = accounts.issue_code(db, user)
    except AccountError as e:
        raise _http_error(e) from e
    background.add_task(accounts.deliver_code, user.email, code)


_FORGOT_REPLY = {"message": "If that email has an account, we've sent a code to it."}


@router.post("/auth/forgot-password", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(body: ForgotPasswordRequest, request: Request, background: BackgroundTasks, db: DbSession):
    """Email a reset code. The answer is identical whether or not the address has an account."""
    enforce(f"forgot:ip:{_ip(request)}", limit=10, window=3600)
    try:
        email = accounts.normalize_email(body.email)
    except AccountError:
        return _FORGOT_REPLY
    enforce(f"forgot:email:{email}", limit=3, window=3600)  # caps how many emails anyone can make us send to one inbox
    user = db.scalar(select(User).where(User.email == email))
    if user is not None:
        code = accounts.issue_reset_code(db, user)
        if code is not None:
            background.add_task(accounts.deliver_reset_code, user.email, code)
    return _FORGOT_REPLY


@router.post("/auth/reset-password", response_model=TokenResponse)
def reset_password(body: ResetPasswordRequest, request: Request, background: BackgroundTasks, db: DbSession):
    """Choose a new password with the emailed code. Signs the person in, and every older session out."""
    enforce(f"reset:ip:{_ip(request)}", limit=20, window=600)
    invalid = HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That code is invalid or has expired. Request a new one.")
    try:
        email = accounts.normalize_email(body.email)
    except AccountError:
        raise invalid from None
    enforce(f"reset:email:{email}", limit=10, window=600)  # the code has 6 digits: guessing must stay expensive
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        raise invalid
    try:
        accounts.reset_password(db, user, body.code, body.new_password)
    except AccountError as e:
        raise _http_error(e) from e
    background.add_task(accounts.deliver_password_changed, user.email)
    return TokenResponse(access_token=create_access_token(user.id), is_verified=True)


@router.get("/me", response_model=UserMe)
def me(user: CurrentUser):
    return user
