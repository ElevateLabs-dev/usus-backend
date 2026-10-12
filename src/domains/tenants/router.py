"""
Organizations router — how the Usus team (platform admins) onboards and
manages client organizations.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import AsyncSessionLocal, get_db
from src.core.dependencies import AuthContext, UserRole, require_roles
from src.domains.tenants import service
from src.domains.tenants.crud import tenant as tenant_repo
from src.domains.tenants.schemas import (
    OrganizationCreate,
    OrganizationDetail,
    OrganizationRead,
    OrganizationUpdate,
)
from src.domains.users import service as users_service

# Session factory used by the background invite task (swapped out in tests).
_session_factory = AsyncSessionLocal

router = APIRouter(prefix="/api/v1/organizations", tags=["Organizations"])

_PlatformAdmin = Annotated[AuthContext, Depends(require_roles(UserRole.PLATFORM_ADMIN))]

_ERRORS: dict[int | str, dict] = {
    401: {"description": "Missing or invalid token"},
    403: {"description": "Caller is not a platform admin"},
}
_NOT_FOUND = {404: {"description": "Organization not found"}}
_CONFLICT = {409: {"description": "Organization name or admin email already in use"}}


@router.post(
    "/",
    response_model=OrganizationDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Onboard an organization",
    description=(
        "**Platform admin only.** One call sets up a new client:\n"
        "1. creates the organization,\n"
        "2. adds the starter scenarios (one per training category),\n"
        "3. creates its first **company admin** and emails them an invite with a "
        "temporary password (they must change it on first sign-in).\n\n"
        "The company admin then adds their own managers and trainees."
    ),
    responses={**_ERRORS, **_CONFLICT},
)
async def create_organization(
    body: OrganizationCreate,
    ctx: _PlatformAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    try:
        tenant, admin = await service.create_organization(db, body)
    except service.OrganizationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    background_tasks.add_task(users_service.send_invites, [admin.id], _session_factory)
    return await service.get_organization_detail(db, tenant.id)


@router.get(
    "/",
    response_model=list[OrganizationRead],
    summary="List organizations",
    description=(
        "**Platform admin only.** Every organization, by name, with its number "
        "of users, trainees, active scenarios and evaluated sessions."
    ),
    responses=_ERRORS,
)
async def list_organizations(
    ctx: _PlatformAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await service.list_organizations(db)


@router.get(
    "/{organization_id}",
    response_model=OrganizationDetail,
    summary="Get an organization",
    description=(
        "**Platform admin only.** The organization's counts plus its company "
        "admins and managers."
    ),
    responses={**_ERRORS, **_NOT_FOUND},
)
async def get_organization(
    organization_id: UUID,
    ctx: _PlatformAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    detail = await service.get_organization_detail(db, organization_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )
    return detail


@router.patch(
    "/{organization_id}",
    response_model=OrganizationDetail,
    summary="Rename or (de)activate an organization",
    description=(
        "**Platform admin only.** Setting `is_active` to false immediately stops "
        "the organization's users from signing in or using the API; setting it "
        "back to true restores access. Nothing is ever deleted."
    ),
    responses={**_ERRORS, **_NOT_FOUND, **_CONFLICT},
)
async def update_organization(
    organization_id: UUID,
    body: OrganizationUpdate,
    ctx: _PlatformAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    tenant = await tenant_repo.get(db, id=organization_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )
    try:
        await service.rename_or_set_active(db, tenant, body.name, body.is_active)
    except service.OrganizationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    return await service.get_organization_detail(db, organization_id)
