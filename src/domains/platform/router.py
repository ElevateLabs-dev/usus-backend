"""
Platform router — what platform admins (the Usus team) use to run the
platform: its health, recent activity, problems to fix, maintenance mode and
the other platform admins.
"""

from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import AsyncSessionLocal, get_db
from src.core.dependencies import AuthContext, UserRole, require_roles
from src.domains.platform import service
from src.domains.platform.schemas import (
    ActivityItem,
    AlertItem,
    PlatformAdminCreate,
    PlatformAdminUpdate,
    PlatformSettingsRead,
    PlatformSettingsUpdate,
    PlatformStatus,
)
from src.domains.users import service as users_service
from src.domains.users.schemas import InviteResendResponse, OrgUserRead

# Session factory used by the background invite task (swapped out in tests).
_session_factory = AsyncSessionLocal

router = APIRouter(prefix="/api/v1/platform", tags=["Platform"])

_PlatformAdmin = Annotated[AuthContext, Depends(require_roles(UserRole.PLATFORM_ADMIN))]

_ERRORS: dict[int | str, dict] = {
    401: {"description": "Missing or invalid token"},
    403: {"description": "Caller is not a platform admin"},
}
_NOT_FOUND = {404: {"description": "Platform admin not found"}}


@router.get(
    "/status",
    response_model=PlatformStatus,
    summary="Platform status",
    description=(
        "**Platform admin only.** Checks the API, the database, email (Resend) "
        "and the AI provider. `overall` is `operational` when every check is "
        "`ok`, `maintenance` while maintenance mode is on, otherwise `degraded`."
    ),
    responses=_ERRORS,
)
async def get_status(
    request: Request,
    ctx: _PlatformAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await service.platform_status(db, request.app.version)


@router.get(
    "/activity",
    response_model=list[ActivityItem],
    summary="Recent activity",
    description=(
        "**Platform admin only.** The latest events across all organizations, "
        "newest first: organizations onboarded, users added and training "
        "sessions completed."
    ),
    responses=_ERRORS,
)
async def get_activity(
    ctx: _PlatformAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    return await service.recent_activity(db, limit)


@router.get(
    "/alerts",
    response_model=list[AlertItem],
    summary="Problems to fix",
    description=(
        "**Platform admin only.** Newest first:\n"
        "- `invite_not_delivered`: an invite email has not gone out after 10 "
        "minutes. Resend it (`POST /organizations/{id}/users/{user_id}/"
        "resend-invite`, or `/platform/admins/{id}/resend-invite`).\n"
        "- `evaluation_missing`: a session ended over 10 minutes ago but has no "
        "evaluation. Re-run it with `POST /evaluations/{session_id}/generate` "
        "(signed in to that organization)."
    ),
    responses=_ERRORS,
)
async def get_alerts(
    ctx: _PlatformAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await service.open_alerts(db)


@router.get(
    "/settings",
    response_model=PlatformSettingsRead,
    summary="Platform settings",
    responses=_ERRORS,
)
async def get_settings(
    ctx: _PlatformAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    row = await service.get_settings(db)
    return PlatformSettingsRead(
        maintenance_mode=row.maintenance_mode, updated_at=row.updated_at
    )


@router.patch(
    "/settings",
    response_model=PlatformSettingsRead,
    summary="Turn maintenance mode on or off",
    description=(
        "**Platform admin only.** While `maintenance_mode` is true, everyone "
        "except platform admins gets **503** when signing in or calling the API."
    ),
    responses=_ERRORS,
)
async def update_settings(
    body: PlatformSettingsUpdate,
    ctx: _PlatformAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    row = await service.set_maintenance_mode(db, body.maintenance_mode)
    return PlatformSettingsRead(
        maintenance_mode=row.maintenance_mode, updated_at=row.updated_at
    )


@router.get(
    "/admins",
    response_model=list[OrgUserRead],
    summary="List platform admins",
    responses=_ERRORS,
)
async def list_admins(
    ctx: _PlatformAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await service.list_platform_admins(db)


@router.post(
    "/admins",
    response_model=OrgUserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a platform admin",
    description=(
        "**Platform admin only.** Creates another member of the Usus team and "
        "emails them a temporary password (changed on first sign-in)."
    ),
    responses={**_ERRORS, 409: {"description": "Email already registered"}},
)
async def add_admin(
    body: PlatformAdminCreate,
    ctx: _PlatformAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    try:
        admin = await service.add_platform_admin(db, body.email, body.full_name)
    except service.PlatformAdminConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    background_tasks.add_task(users_service.send_invites, [admin.id], _session_factory)
    return admin


@router.patch(
    "/admins/{user_id}",
    response_model=OrgUserRead,
    summary="Rename or (de)activate a platform admin",
    responses={
        **_ERRORS,
        **_NOT_FOUND,
        400: {"description": "You cannot deactivate yourself"},
    },
)
async def update_admin(
    user_id: UUID,
    body: PlatformAdminUpdate,
    ctx: _PlatformAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    admin = await service.get_platform_admin(db, user_id)
    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Platform admin not found"
        )
    if body.is_active is False and admin.id == ctx.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate yourself",
        )

    if body.full_name is not None:
        admin.full_name = body.full_name.strip() or None
    if body.is_active is not None:
        admin.is_active = body.is_active
    await db.commit()
    await db.refresh(admin)
    return admin


@router.post(
    "/admins/{user_id}/resend-invite",
    response_model=InviteResendResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Resend a platform admin's invite",
    description=(
        "**Platform admin only.** Emails a new temporary password, replacing the "
        "old one."
    ),
    responses={**_ERRORS, **_NOT_FOUND},
)
async def resend_admin_invite(
    user_id: UUID,
    ctx: _PlatformAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    admin = await service.get_platform_admin(db, user_id)
    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Platform admin not found"
        )

    background_tasks.add_task(users_service.send_invites, [admin.id], _session_factory)
    return InviteResendResponse(status="sending", email=admin.email)
