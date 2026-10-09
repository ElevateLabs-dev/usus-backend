from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import (
    AuthContext,
    UserRole,
    get_auth_context,
    require_roles,
)
from src.domains.progress import service
from src.domains.progress.schemas import ProgressReport, TraineeSummary
from src.domains.users.crud import user as user_repo

router = APIRouter(prefix="/api/v1/progress", tags=["Progress"])

_OrgStaff = Annotated[
    AuthContext,
    Depends(
        require_roles(UserRole.COMPANY_ADMIN, UserRole.MANAGER, UserRole.PLATFORM_ADMIN)
    ),
]

_AUTH_ERRORS: dict[int | str, dict] = {
    401: {"description": "Missing/invalid token, or no organization in the token"},
    403: {"description": "Not allowed, or password change required"},
}


def _tenant_of(ctx: AuthContext) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant context required",
        )
    return ctx.tenant_id


@router.get(
    "/me",
    response_model=ProgressReport,
    summary="Your training progress",
    description=(
        "Dashboard data for the signed-in user: sessions completed, practice "
        "time, average / best / latest score, whether scores are improving, the "
        "score over time (for a chart), the 7 dimensions (average, latest, "
        "change) and per-category averages."
    ),
    responses=_AUTH_ERRORS,
)
async def my_progress(
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await service.build_report(db, _tenant_of(ctx), ctx.user_id)


@router.get(
    "/team",
    response_model=list[TraineeSummary],
    summary="Your organization's trainees at a glance",
    description=(
        "**Company admin / manager only.** Every trainee with sessions completed, "
        "average and latest score, and last activity. `must_change_password` "
        "true means they have not signed in yet."
    ),
    responses=_AUTH_ERRORS,
)
async def team_progress(
    ctx: _OrgStaff,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await service.team_overview(db, _tenant_of(ctx))


@router.get(
    "/users/{user_id}",
    response_model=ProgressReport,
    summary="A trainee's progress",
    description=(
        "**Company admin / manager only.** The same report as `GET /progress/me` "
        "for a user in your organization."
    ),
    responses={**_AUTH_ERRORS, 404: {"description": "User not in your organization"}},
)
async def user_progress(
    user_id: UUID,
    ctx: _OrgStaff,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    tenant_id = _tenant_of(ctx)
    user = await user_repo.get(db, id=user_id)
    if user is None or user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return await service.build_report(db, tenant_id, user_id)
