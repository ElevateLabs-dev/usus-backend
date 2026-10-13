"""
Users router — organizations add and manage their own trainees.

Trainees cannot self-register. A company admin or manager adds them (one by
one, as a JSON batch, or from an Excel/CSV file); each trainee is emailed a
temporary password and must replace it on first sign-in
(see POST /auth/change-password).
"""

from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import AsyncSessionLocal, get_db
from src.core.dependencies import (
    AuthContext,
    UserRole,
    get_auth_context_allow_password_change,
    require_roles,
)
from src.domains.users import service
from src.domains.users.crud import user as user_repo
from src.domains.users.schemas import (
    MAX_BULK_TRAINEES,
    BulkTraineeCreate,
    BulkTraineeResult,
    ErrorResponse,
    InviteResendResponse,
    OrgUserRead,
    OrgUserUpdate,
    ProfileUpdate,
    TraineeCreate,
    UserInvite,
)

# Session factory used by the background invite task (swapped out in tests).
_session_factory = AsyncSessionLocal

_MAX_UPLOAD_BYTES = 2_000_000  # 2 MB is far more than 500 rows of email,name
_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

router = APIRouter(prefix="/api/v1/users", tags=["Users & Trainees"])

_OrgStaff = Annotated[
    AuthContext,
    Depends(
        require_roles(UserRole.COMPANY_ADMIN, UserRole.MANAGER, UserRole.PLATFORM_ADMIN)
    ),
]


def _error(description: str, example: str) -> dict:
    return {
        "model": ErrorResponse,
        "description": description,
        "content": {"application/json": {"example": {"detail": example}}},
    }


# Errors shared by every endpoint restricted to company admins / managers.
_STAFF_ERRORS: dict[int | str, dict] = {
    401: _error(
        "Missing or invalid token, or the token has no organization",
        "Could not validate credentials",
    ),
    403: _error(
        "Not a company admin or manager, or the password must be changed first",
        "Role 'trainee' is not authorised for this action. "
        "Required: ['company_admin', 'manager', 'platform_admin']",
    ),
}


def _tenant_of(ctx: AuthContext) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant context required",
        )
    return ctx.tenant_id


def _schedule_invites(background_tasks: BackgroundTasks, user_ids: list[UUID]) -> None:
    if user_ids:
        background_tasks.add_task(service.send_invites, user_ids, _session_factory)


def _can_manage(ctx: AuthContext, target_role: str) -> bool:
    """Company (and platform) admins manage every organization role; managers
    only manage trainees. Platform admins are never managed here."""
    if target_role == UserRole.PLATFORM_ADMIN.value:
        return False
    if ctx.role in (UserRole.COMPANY_ADMIN, UserRole.PLATFORM_ADMIN):
        return True
    return target_role == UserRole.TRAINEE.value


async def _managed_user(db: AsyncSession, ctx: AuthContext, user_id: UUID):
    """A user in the caller's organization that the caller may manage (or 404)."""
    user = await user_repo.get(db, id=user_id)
    if (
        user is None
        or user.tenant_id != _tenant_of(ctx)
        or not _can_manage(ctx, user.role)
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return user


@router.get(
    "/me",
    response_model=OrgUserRead,
    summary="Get your profile",
    description=(
        "Returns the signed-in user's basic profile.\n\n"
        "Works even while `must_change_password` is true, so the frontend can "
        "show the user who they are on the change-password screen."
    ),
    responses={401: _STAFF_ERRORS[401]},
)
async def get_me(
    ctx: Annotated[AuthContext, Depends(get_auth_context_allow_password_change)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = await user_repo.get(db, id=ctx.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return user


@router.get(
    "/",
    response_model=list[OrgUserRead],
    summary="List your organization's users",
    description=(
        "**Company admin / manager only.** Newest first.\n\n"
        "Use `must_change_password` to see who has not signed in yet, and "
        "`invite_sent_at` (null) to see whose invite email failed — resend it "
        "with `POST /users/{user_id}/resend-invite`."
    ),
    responses=_STAFF_ERRORS,
)
async def list_users(
    ctx: _OrgStaff,
    db: Annotated[AsyncSession, Depends(get_db)],
    role: Annotated[
        UserRole | None, Query(description="Only return users with this role")
    ] = None,
):
    return await service.list_tenant_users(db, _tenant_of(ctx), role)


@router.patch(
    "/me",
    response_model=OrgUserRead,
    summary="Update your profile",
    description="Change your own display name.",
    responses={401: _STAFF_ERRORS[401]},
)
async def update_me(
    body: ProfileUpdate,
    ctx: Annotated[AuthContext, Depends(get_auth_context_allow_password_change)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = await user_repo.get(db, id=ctx.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    user.full_name = body.full_name.strip()
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post(
    "/",
    response_model=OrgUserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Invite a user (trainee, manager or company admin)",
    description=(
        "Creates a user in your organization with the given role and emails them "
        "a temporary password; they must change it on first sign-in.\n\n"
        "- **Company admins** can invite trainees, managers and other company "
        "admins.\n"
        "- **Managers** can only invite trainees.\n\n"
        "For many trainees at once use `/users/trainees/bulk` or "
        "`/users/trainees/import`."
    ),
    responses={
        **_STAFF_ERRORS,
        409: _error("The email is already registered", "Email already registered"),
    },
)
async def invite_user(
    body: UserInvite,
    ctx: _OrgStaff,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    tenant_id = _tenant_of(ctx)
    if not _can_manage(ctx, body.role.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Managers can only invite trainees",
        )

    created, skipped = await service.add_users(
        db,
        tenant_id,
        [TraineeCreate(email=body.email, full_name=body.full_name)],
        UserRole(body.role.value),
    )
    if not created:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=skipped[0].reason
        )

    _schedule_invites(background_tasks, [created[0].id])
    return created[0]


@router.post(
    "/trainees",
    response_model=OrgUserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add one trainee",
    description=(
        "**Company admin / manager only.** Creates a trainee in your organization "
        "and emails them a temporary password in the background. The email is "
        "stored lower-case.\n\n"
        "The trainee must change the password on first sign-in."
    ),
    responses={
        **_STAFF_ERRORS,
        409: _error("The email is already registered", "Email already registered"),
    },
)
async def add_trainee(
    body: TraineeCreate,
    ctx: _OrgStaff,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    created, skipped = await service.add_trainees(db, _tenant_of(ctx), [body])
    if not created:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=skipped[0].reason
        )

    _schedule_invites(background_tasks, [created[0].id])
    return created[0]


@router.post(
    "/trainees/bulk",
    response_model=BulkTraineeResult,
    status_code=status.HTTP_201_CREATED,
    summary="Add many trainees (JSON)",
    description=(
        f"**Company admin / manager only.** Up to {MAX_BULK_TRAINEES} trainees per "
        "request. Every new trainee is emailed an invite.\n\n"
        "Emails that are already registered, or repeated in the same request, are "
        "returned in `skipped` with a reason; the rest are created."
    ),
    responses=_STAFF_ERRORS,
)
async def add_trainees_bulk(
    body: BulkTraineeCreate,
    ctx: _OrgStaff,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    created, skipped = await service.add_trainees(db, _tenant_of(ctx), body.trainees)
    _schedule_invites(background_tasks, [u.id for u in created])
    return BulkTraineeResult(created=created, skipped=skipped)


@router.get(
    "/trainees/import-template",
    summary="Download the Excel import template",
    description=(
        "**Company admin / manager only.** An `.xlsx` file with the columns "
        "`email` and `full_name` and one example row. Fill it in and upload it "
        "to `POST /users/trainees/import`."
    ),
    response_class=Response,
    responses={
        200: {
            "description": "Excel template",
            "content": {_XLSX_MEDIA_TYPE: {}},
        },
        **_STAFF_ERRORS,
    },
)
async def download_import_template(ctx: _OrgStaff):
    return Response(
        content=service.build_import_template(),
        media_type=_XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": 'attachment; filename="usus-trainees-template.xlsx"'
        },
    )


@router.post(
    "/trainees/import",
    response_model=BulkTraineeResult,
    status_code=status.HTTP_201_CREATED,
    summary="Add many trainees from an Excel or CSV file",
    description=(
        "**Company admin / manager only.** Upload an **Excel (.xlsx)** file "
        "(first sheet is read) or a **CSV**, max 2 MB and "
        f"{MAX_BULK_TRAINEES} trainees.\n\n"
        "The first row must be headers:\n"
        "- `email` — required (also accepted: `Email Address`, `E-mail`)\n"
        "- `full_name` — optional (also accepted: `Full Name`, `Name`)\n\n"
        "Blank rows are ignored. Invalid emails, duplicates and already-registered "
        "emails are returned in `skipped`; everyone else is created and emailed "
        "an invite. Get a ready-made file from `GET /users/trainees/import-template`."
    ),
    responses={
        **_STAFF_ERRORS,
        400: _error(
            "Unsupported or unreadable file, missing email column, or too many rows",
            "The first row must contain an 'email' column header",
        ),
        413: _error("File is larger than 2 MB", "File is larger than 2 MB"),
    },
)
async def import_trainees(
    ctx: _OrgStaff,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(description="The trainee list (.xlsx or .csv)")],
):
    tenant_id = _tenant_of(ctx)
    content = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File is larger than 2 MB",
        )

    try:
        entries, invalid = service.parse_trainee_file(file.filename or "", content)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    created, skipped = await service.add_trainees(db, tenant_id, entries)
    _schedule_invites(background_tasks, [u.id for u in created])
    return BulkTraineeResult(created=created, skipped=invalid + skipped)


@router.post(
    "/{user_id}/resend-invite",
    response_model=InviteResendResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Resend a user's invite (or reset their password)",
    description=(
        "**Company admin / manager only.** Generates a new temporary password, "
        "emails it, and requires the user to change it at next sign-in. Any "
        "previous password stops working.\n\n"
        "Use it when an invite email failed (`invite_sent_at` is null) or someone "
        "forgot their password. Managers can do this for trainees; company "
        "admins for anyone in the organization."
    ),
    responses={
        **_STAFF_ERRORS,
        404: _error("No such user that you can manage", "User not found"),
    },
)
async def resend_invite(
    user_id: UUID,
    ctx: _OrgStaff,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    user = await _managed_user(db, ctx, user_id)

    _schedule_invites(background_tasks, [user.id])
    return InviteResendResponse(status="sending", email=user.email)


@router.patch(
    "/{user_id}",
    response_model=OrgUserRead,
    summary="Edit, deactivate or change the role of a user",
    description=(
        "Send only the fields you want to change.\n\n"
        "- **Company admins** can edit anyone in their organization, including "
        "changing roles.\n"
        "- **Managers** can edit and deactivate trainees, but cannot change "
        "roles.\n\n"
        "Deactivating takes effect immediately and keeps all of the user's "
        "training history. You cannot deactivate yourself, change your own role, "
        "or remove an organization's last active company admin."
    ),
    responses={
        **_STAFF_ERRORS,
        400: _error(
            "Trying to deactivate yourself or change your own role",
            "You cannot deactivate yourself",
        ),
        404: _error("No such user that you can manage", "User not found"),
        409: _error(
            "Would leave the organization without an active company admin",
            "An organization needs at least one active company admin",
        ),
    },
)
async def update_user(
    user_id: UUID,
    body: OrgUserUpdate,
    ctx: _OrgStaff,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = await _managed_user(db, ctx, user_id)
    changes = body.model_dump(exclude_unset=True)
    new_role = changes.get("role")
    deactivating = changes.get("is_active") is False

    if user.id == ctx.user_id:
        if deactivating:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot deactivate yourself",
            )
        if new_role is not None and new_role.value != user.role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot change your own role",
            )

    if new_role is not None and new_role.value != user.role:
        if ctx.role == UserRole.MANAGER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Managers cannot change roles",
            )

    losing_admin = user.role == UserRole.COMPANY_ADMIN.value and (
        deactivating
        or (new_role is not None and new_role.value != UserRole.COMPANY_ADMIN.value)
    )
    if losing_admin and not await service.has_other_active_admin(db, user):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An organization needs at least one active company admin",
        )

    if "full_name" in changes:
        user.full_name = (changes["full_name"] or "").strip() or None
    if new_role is not None:
        user.role = new_role.value
    if changes.get("is_active") is not None:
        user.is_active = changes["is_active"]

    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
