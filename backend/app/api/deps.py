from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_token_claims
from app.db.session import get_db
from app.models import User

DbSession = Annotated[Session, Depends(get_db)]
_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    db: DbSession,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if creds is None:
        raise unauthorized
    claims = decode_token_claims(creds.credentials)
    user = db.get(User, claims[0]) if claims is not None else None
    if user is None or user.deleted_at is not None:
        raise unauthorized
    # A password change signs out everything issued before it (a stolen token dies with the old password).
    if user.password_changed_at is not None and claims[1] < int(user.password_changed_at.timestamp()):
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_verified(user: CurrentUser) -> User:
    """Gate for actions that need a proven campus email (listing, bidding)."""
    if not user.is_verified:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            {"code": "email_not_verified", "message": "Verify your campus email to list or bid"},
        )
    return user


VerifiedUser = Annotated[User, Depends(require_verified)]
