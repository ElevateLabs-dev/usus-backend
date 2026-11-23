"""
Getting started: the company setup checklist and the first-time walkthrough.

Nothing here blocks the platform; the checklist only shows what is left. Each
step is worked out from the organization's data, so organizations created
before the checklist see their real progress too.
"""

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import (
    AuthContext,
    UserRole,
    get_auth_context,
    require_roles,
)
from src.domains.knowledge.service import ready_count
from src.domains.scenarios.defaults import DEFAULT_SCENARIOS
from src.domains.scenarios.models import Scenario
from src.domains.tenants.models import Tenant
from src.domains.users.models import User

router = APIRouter(prefix="/api/v1/onboarding", tags=["Getting started"])

_Staff = Annotated[
    AuthContext, Depends(require_roles(UserRole.COMPANY_ADMIN, UserRole.MANAGER))
]
_Admin = Annotated[AuthContext, Depends(require_roles(UserRole.COMPANY_ADMIN))]


class ChecklistStep(BaseModel):
    key: str
    title: str
    description: str
    done: bool


class Checklist(BaseModel):
    steps: list[ChecklistStep]
    completed: int
    total: int
    launched_at: datetime | None
    dismissed: bool = Field(description="The company admin hid the checklist")


class ChecklistUpdate(BaseModel):
    dismissed: bool


class WalkthroughDone(BaseModel):
    walkthrough_done_at: datetime


async def _checklist(db: AsyncSession, tenant: Tenant) -> Checklist:
    starter_names = [s.name for s in DEFAULT_SCENARIOS]
    own_scenarios = await db.execute(
        select(func.count(Scenario.id)).where(
            Scenario.tenant_id == tenant.id,
            Scenario.is_archived.is_(False),
            Scenario.name.not_in(starter_names),
        )
    )
    trainees = await db.execute(
        select(func.count(User.id)).where(
            User.tenant_id == tenant.id, User.role == UserRole.TRAINEE.value
        )
    )
    steps = [
        ChecklistStep(
            key="knowledge_base",
            title="Upload your knowledge base",
            description="Add your policies and documents (PDF or Word).",
            done=await ready_count(db, tenant.id) > 0,
        ),
        ChecklistStep(
            key="scenarios",
            title="Create scenarios",
            description="Generate scenarios from your documents or write your own.",
            done=own_scenarios.scalar_one() > 0,
        ),
        ChecklistStep(
            key="company_profile",
            title="Set up your company account",
            description="Add your logo and company details.",
            done=bool(tenant.logo_key and tenant.company_type),
        ),
        ChecklistStep(
            key="team",
            title="Add your team",
            description="Invite trainees and put them in teams.",
            done=trainees.scalar_one() > 0,
        ),
        ChecklistStep(
            key="launch",
            title="Review and launch",
            description="Check everything and start training.",
            done=tenant.launched_at is not None,
        ),
    ]
    return Checklist(
        steps=steps,
        completed=sum(step.done for step in steps),
        total=len(steps),
        launched_at=tenant.launched_at,
        dismissed=tenant.checklist_dismissed_at is not None,
    )


async def _tenant(db: AsyncSession, tenant_id: UUID | None) -> Tenant:
    tenant = await db.get(Tenant, tenant_id) if tenant_id else None
    if tenant is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return tenant


@router.get(
    "/checklist",
    response_model=Checklist,
    summary="Company setup checklist",
    description=(
        "**Company admin / manager only.** The 5 setup steps and which are done, "
        "for the progress bar. Optional: nothing is blocked until it is done."
    ),
)
async def get_checklist(ctx: _Staff, db: Annotated[AsyncSession, Depends(get_db)]):
    return await _checklist(db, await _tenant(db, ctx.tenant_id))


@router.patch(
    "/checklist",
    response_model=Checklist,
    summary="Hide or show the checklist",
    description="**Company admin only.**",
)
async def update_checklist(
    body: ChecklistUpdate,
    ctx: _Admin,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    tenant = await _tenant(db, ctx.tenant_id)
    tenant.checklist_dismissed_at = (
        datetime.now(timezone.utc) if body.dismissed else None
    )
    await db.commit()
    return await _checklist(db, tenant)


@router.post(
    "/launch",
    response_model=Checklist,
    summary="Launch",
    description=(
        "**Company admin only.** Marks the last checklist step done. It does not "
        "require the other steps."
    ),
)
async def launch(ctx: _Admin, db: Annotated[AsyncSession, Depends(get_db)]):
    tenant = await _tenant(db, ctx.tenant_id)
    if tenant.launched_at is None:
        tenant.launched_at = datetime.now(timezone.utc)
        await db.commit()
    return await _checklist(db, tenant)


@router.post(
    "/walkthrough",
    response_model=WalkthroughDone,
    status_code=status.HTTP_200_OK,
    summary="Finish the walkthrough",
    description=(
        "Any user: call when they finish or skip the first-time walkthrough. "
        "`GET /users/me` then has `walkthrough_done_at`, so it is not shown again."
    ),
)
async def finish_walkthrough(
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = await db.get(User, ctx.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.walkthrough_done_at is None:
        user.walkthrough_done_at = datetime.now(timezone.utc)
        await db.commit()
    return WalkthroughDone(walkthrough_done_at=user.walkthrough_done_at)
