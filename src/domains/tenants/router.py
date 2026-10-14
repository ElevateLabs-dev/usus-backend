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
    CompanyAdminCreate,
    OrganizationCreate,
    OrganizationDetail,
    OrganizationRead,
    OrganizationRename,
    OrganizationUpdate,
    StaffUpdate,
)
from src.domains.users import service as users_service
from src.domains.users.models import User
from src.domains.users.schemas import InviteResendResponse, OrgUserRead, TraineeCreate

# Session factory used by the background invite task (swapped out in tests).
_session_factory = AsyncSessionLocal

router = APIRouter(prefix="/api/v1/organizations", tags=["Organizations"])

_PlatformAdmin = Annotated[AuthContext, Depends(require_roles(UserRole.PLATFORM_ADMIN))]
_OrgStaff = Annotated[
    AuthContext, Depends(require_roles(UserRole.COMPANY_ADMIN, UserRole.MANAGER))
]
_CompanyAdmin = Annotated[AuthContext, Depends(require_roles(UserRole.COMPANY_ADMIN))]

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


# /me is declared before /{organization_id} so "me" is not read as an id.
@router.get(
    "/me",
    response_model=OrganizationDetail,
    summary="Your organization",
    description=(
        "**Company admin / manager only.** Your organization's name, status and "
        "counts (users, trainees, active scenarios, completed sessions), plus "
        "its company admins and managers."
    ),
    responses={
        401: {"description": "Missing or invalid token"},
        403: {"description": "Not a company admin or manager"},
    },
)
async def get_my_organization(
    ctx: _OrgStaff,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await service.get_organization_detail(db, ctx.tenant_id)


@router.patch(
    "/me",
    response_model=OrganizationDetail,
    summary="Rename your organization",
    description="**Company admin only.** The name must not be used by another "
    "organization.",
    responses={
        401: {"description": "Missing or invalid token"},
        403: {"description": "Not a company admin"},
        409: {"description": "Another organization already has this name"},
    },
)
async def rename_my_organization(
    body: OrganizationRename,
    ctx: _CompanyAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    tenant = await tenant_repo.get(db, id=ctx.tenant_id)
    try:
        await service.rename_or_set_active(db, tenant, body.name, None)
    except service.OrganizationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    return await service.get_organization_detail(db, ctx.tenant_id)


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


async def _organization_or_404(db: AsyncSession, organization_id: UUID):
    tenant = await tenant_repo.get(db, id=organization_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )
    return tenant


async def _member_or_404(db: AsyncSession, organization_id: UUID, user_id: UUID):
    await _organization_or_404(db, organization_id)
    user = await db.get(User, user_id)
    if user is None or user.tenant_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return user


@router.post(
    "/{organization_id}/admins",
    response_model=OrgUserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a company admin",
    description=(
        "**Platform admin only.** Adds another company admin to the "
        "organization and emails them a temporary password."
    ),
    responses={
        **_ERRORS,
        **_NOT_FOUND,
        409: {"description": "Email already registered"},
    },
)
async def add_company_admin(
    organization_id: UUID,
    body: CompanyAdminCreate,
    ctx: _PlatformAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    await _organization_or_404(db, organization_id)
    created, skipped = await users_service.add_users(
        db,
        organization_id,
        [TraineeCreate(email=body.email, full_name=body.full_name)],
        UserRole.COMPANY_ADMIN,
    )
    if not created:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=skipped[0].reason
        )

    background_tasks.add_task(
        users_service.send_invites, [created[0].id], _session_factory
    )
    return created[0]


@router.post(
    "/{organization_id}/users/{user_id}/resend-invite",
    response_model=InviteResendResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Resend an invite for a user in an organization",
    description=(
        "**Platform admin only.** Emails the user a new temporary password, "
        "replacing the old one. Use it when `invite_sent_at` is null (the email "
        "failed) or a company admin is locked out."
    ),
    responses={**_ERRORS, 404: {"description": "Organization or user not found"}},
)
async def resend_member_invite(
    organization_id: UUID,
    user_id: UUID,
    ctx: _PlatformAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    user = await _member_or_404(db, organization_id, user_id)
    background_tasks.add_task(users_service.send_invites, [user.id], _session_factory)
    return InviteResendResponse(status="sending", email=user.email)


@router.patch(
    "/{organization_id}/users/{user_id}",
    response_model=OrgUserRead,
    summary="(De)activate a user in an organization",
    description=(
        "**Platform admin only.** An organization must keep at least one active "
        "company admin."
    ),
    responses={
        **_ERRORS,
        404: {"description": "Organization or user not found"},
        409: {"description": "This is the organization's last active company admin"},
    },
)
async def update_member(
    organization_id: UUID,
    user_id: UUID,
    body: StaffUpdate,
    ctx: _PlatformAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = await _member_or_404(db, organization_id, user_id)
    if (
        not body.is_active
        and user.is_active
        and user.role == UserRole.COMPANY_ADMIN.value
        and not await users_service.has_other_active_admin(db, user)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An organization needs at least one active company admin",
        )

    user.is_active = body.is_active
    await db.commit()
    await db.refresh(user)
    return user
