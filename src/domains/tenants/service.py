"""Organization onboarding and overview for platform admins."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import UserRole
from src.domains.evaluations.models import EvaluationResult
from src.domains.scenarios.crud import scenario as scenario_repo
from src.domains.scenarios.models import Scenario
from src.domains.scenarios.service import ScenarioService
from src.domains.tenants.models import Tenant
from src.domains.tenants.schemas import (
    OrganizationCreate,
    OrganizationDetail,
    OrganizationRead,
)
from src.domains.users import service as users_service
from src.domains.users.models import User
from src.domains.users.schemas import OrgUserRead, TraineeCreate


class OrganizationConflictError(Exception):
    """The organization name or the admin's email is already in use."""


async def _name_taken(
    db: AsyncSession, name: str, exclude_id: uuid.UUID | None = None
) -> bool:
    query = select(Tenant.id).where(func.lower(Tenant.name) == name.strip().lower())
    if exclude_id is not None:
        query = query.where(Tenant.id != exclude_id)
    return (await db.execute(query)).first() is not None


async def create_organization(
    db: AsyncSession, data: OrganizationCreate
) -> tuple[Tenant, User]:
    """
    Onboard an organization: create it, seed its starter scenarios and create
    its first company admin (locked until the invite email sets a temporary
    password — see users.service.send_invites).

    Raises OrganizationConflictError before creating anything if the name or
    the admin's email is already in use.
    """
    if await _name_taken(db, data.name):
        raise OrganizationConflictError("An organization with this name already exists")

    email = data.admin_email.strip().lower()
    existing_user = await db.execute(
        select(User.id).where(func.lower(User.email) == email)
    )
    if existing_user.first() is not None:
        raise OrganizationConflictError("The admin's email is already registered")

    tenant = Tenant(name=data.name.strip())
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)

    await ScenarioService(scenario_repo).seed_defaults(db, tenant.id)

    created, _ = await users_service.add_users(
        db,
        tenant.id,
        [TraineeCreate(email=email, full_name=data.admin_full_name)],
        UserRole.COMPANY_ADMIN,
    )
    return tenant, created[0]


async def rename_or_set_active(
    db: AsyncSession, tenant: Tenant, name: str | None, is_active: bool | None
) -> Tenant:
    if name is not None and name.strip() != tenant.name:
        if await _name_taken(db, name, exclude_id=tenant.id):
            raise OrganizationConflictError(
                "An organization with this name already exists"
            )
        tenant.name = name.strip()
    if is_active is not None:
        tenant.is_active = is_active
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return tenant


async def _counts(db: AsyncSession, query) -> dict[uuid.UUID, int]:
    return {tenant_id: count for tenant_id, count in (await db.execute(query)).all()}


async def list_organizations(
    db: AsyncSession, only: uuid.UUID | None = None
) -> list[OrganizationRead]:
    """All organizations (or just one) with their usage counts."""
    tenants_query = select(Tenant).order_by(Tenant.name)
    if only is not None:
        tenants_query = tenants_query.where(Tenant.id == only)
    tenants = (await db.execute(tenants_query)).scalars().all()

    users = await _counts(
        db, select(User.tenant_id, func.count(User.id)).group_by(User.tenant_id)
    )
    trainees = await _counts(
        db,
        select(User.tenant_id, func.count(User.id))
        .where(User.role == UserRole.TRAINEE.value)
        .group_by(User.tenant_id),
    )
    scenarios = await _counts(
        db,
        select(Scenario.tenant_id, func.count(Scenario.id))
        .where(Scenario.is_archived.is_(False))
        .group_by(Scenario.tenant_id),
    )
    sessions = await _counts(
        db,
        select(EvaluationResult.tenant_id, func.count(EvaluationResult.id)).group_by(
            EvaluationResult.tenant_id
        ),
    )

    return [
        OrganizationRead(
            id=tenant.id,
            name=tenant.name,
            is_active=tenant.is_active,
            created_at=tenant.created_at,
            users_count=users.get(tenant.id, 0),
            trainees_count=trainees.get(tenant.id, 0),
            scenarios_count=scenarios.get(tenant.id, 0),
            sessions_completed=sessions.get(tenant.id, 0),
        )
        for tenant in tenants
    ]


async def get_organization_detail(
    db: AsyncSession, tenant_id: uuid.UUID
) -> OrganizationDetail | None:
    summary = await list_organizations(db, only=tenant_id)
    if not summary:
        return None
    staff = (
        (
            await db.execute(
                select(User)
                .where(
                    User.tenant_id == tenant_id,
                    User.role.in_(
                        [UserRole.COMPANY_ADMIN.value, UserRole.MANAGER.value]
                    ),
                )
                .order_by(User.created_at)
            )
        )
        .scalars()
        .all()
    )
    return OrganizationDetail(
        **summary[0].model_dump(),
        staff=[OrgUserRead.model_validate(user) for user in staff],
    )
