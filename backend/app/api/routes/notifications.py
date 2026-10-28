from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.notification import MarkAllResult, NotificationFeed, NotificationOut
from app.services import notifications as service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationFeed)
def list_notifications(
    user: CurrentUser,
    db: DbSession,
    since_id: Annotated[
        int | None,
        Query(ge=0, description="Polling cursor: only notifications with a higher id, oldest first"),
    ] = None,
    before_id: Annotated[int | None, Query(ge=1, description="History paging: only notifications older than this id")] = None,
    unread_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    """My notifications. Newest first by default; with `since_id`, a cursor feed for polling."""
    items = service.list_for_user(db, user.id, since_id, unread_only, limit, before_id)
    return NotificationFeed(
        items=items,
        unread_count=service.unread_count(db, user.id),
        latest_id=max((n.id for n in items), default=None),
        oldest_id=min((n.id for n in items), default=None),
    )


@router.post("/read-all", response_model=MarkAllResult)
def read_all(user: CurrentUser, db: DbSession):
    return MarkAllResult(marked=service.mark_all_read(db, user.id))


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def read_one(notification_id: int, user: CurrentUser, db: DbSession):
    # Someone else's notification looks exactly like a missing one.
    if not service.mark_read(db, user.id, notification_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
