from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.clock import utcnow
from app.core.ratelimit import enforce
from app.core.security import create_access_token, hash_password, verify_password
from app.models import AutoBid
from app.schemas.auth import TokenResponse, UserMe
from app.schemas.bid import MyAutoBid
from app.schemas.listing import ListingPage, MyBid
from app.schemas.profile import PasswordChange, ProfileSummary, ProfileUpdate
from app.services import accounts
from app.services import listings as listing_service
from app.services import profile as profile_service

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/listings", response_model=ListingPage)
def my_listings(
    user: CurrentUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Everything I'm selling, in any status, newest first."""
    return listing_service.search_listings(
        db,
        status=None,
        seller_id=user.id,
        sort=listing_service.Sort.newest,
        limit=limit,
        offset=offset,
    )


@router.get("/bids", response_model=list[MyBid])
def my_bids(user: CurrentUser, db: DbSession):
    """Every listing I've bid on, with my best bid and whether I'm currently leading."""
    return listing_service.my_bids(db, user.id)


@router.get("/auto-bids", response_model=list[MyAutoBid])
def my_auto_bids(user: CurrentUser, db: DbSession):
    """My standing maximums, so the UI can show which auctions I have one on."""
    rows = db.scalars(select(AutoBid).where(AutoBid.user_id == user.id)).all()
    return [MyAutoBid(listing_id=a.listing_id, max_amount=a.max_amount) for a in rows]


@router.patch("", response_model=UserMe)
def update_profile(body: ProfileUpdate, user: CurrentUser, db: DbSession):
    """Change my name, department or year. Only what I send changes; department/year can be cleared with null."""
    enforce(f"profile:user:{user.id}", limit=10, window=3600)
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "No changes given")
    if "display_name" in changes:
        user.display_name = changes["display_name"].strip()
    if "department" in changes:
        user.department = (changes["department"] or "").strip() or None
    if "year_of_study" in changes:
        user.year_of_study = changes["year_of_study"]
    db.commit()
    return user


@router.post("/password", response_model=TokenResponse)
def change_password(body: PasswordChange, user: CurrentUser, background: BackgroundTasks, db: DbSession):
    """Change my password. Needs the current one; every other device is signed out, and I get a fresh token."""
    enforce(f"password:user:{user.id}", limit=10, window=600)  # slows guessing the current password
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your current password is not correct")
    if body.new_password == body.current_password:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose a password different from your current one")
    user.password_hash = hash_password(body.new_password)
    user.password_changed_at = utcnow()
    db.commit()
    background.add_task(accounts.deliver_password_changed, user.email)
    return TokenResponse(access_token=create_access_token(user.id), is_verified=user.is_verified)


@router.get("/summary", response_model=ProfileSummary)
def my_summary(user: CurrentUser, db: DbSession):
    """My numbers: what I'm selling and what I'm bidding on."""
    return profile_service.build_summary(db, user.id)
