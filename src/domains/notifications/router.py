from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import AuthContext, get_auth_context
from src.domains.notifications import service
from src.domains.notifications.schemas import NotificationList, NotificationRead

router = APIRouter(prefix="/api/v1/notifications", tags=["Notifications"])

_User = Annotated[AuthContext, Depends(get_auth_context)]


@router.get(
    "/",
    response_model=NotificationList,
    summary="Your notifications",
    description="The latest 50 notifications, newest first, and the unread count.",
)
async def list_notifications(
    ctx: _User, db: Annotated[AsyncSession, Depends(get_db)]
):
    items, unread_count = await service.list_for_user(db, ctx.user_id)
    return NotificationList(items=items, unread_count=unread_count)


@router.post(
    "/read-all",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark all notifications as read",
)
async def read_all(ctx: _User, db: Annotated[AsyncSession, Depends(get_db)]):
    await service.mark_all_read(db, ctx.user_id)


@router.post(
    "/{notification_id}/read",
    response_model=NotificationRead,
    summary="Mark a notification as read",
    responses={404: {"description": "Notification not found"}},
)
async def read_one(
    notification_id: UUID,
    ctx: _User,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    notification = await service.mark_read(db, ctx.user_id, notification_id)
    if notification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found"
        )
    return notification
