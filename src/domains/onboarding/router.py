"""
Getting started: the company setup checklist.

Nothing here blocks the platform; the checklist only shows what is left. Each
step is ticked off from the organization's data as it gets done, so
organizations created before the checklist see their real progress too.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import AuthContext, UserRole, require_roles
from src.domains.knowledge.service import ready_count
from src.domains.scenarios.defaults import DEFAULT_SCENARIOS
from src.domains.scenarios.models import Scenario
from src.domains.tenants.models import Tenant
from src.domains.users.models import User

router = APIRouter(prefix="/api/v1/onboarding", tags=["Getting started"])

_Staff = Annotated[
    AuthContext, Depends(require_roles(UserRole.COMPANY_ADMIN, UserRole.MANAGER))
]


class ChecklistStep(BaseModel):
    key: str
    title: str
    description: str
    done: bool


class Checklist(BaseModel):
    steps: list[ChecklistStep]
    completed: int
    total: int


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
    ]
    return Checklist(
        steps=steps,
        completed=sum(step.done for step in steps),
        total=len(steps),
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
        "**Company admin / manager only.** The setup steps and which are done, "
        "for the progress bar. Each step is ticked off as soon as it is done. "
        "Optional: nothing is blocked until it is done."
    ),
)
async def get_checklist(ctx: _Staff, db: Annotated[AsyncSession, Depends(get_db)]):
    return await _checklist(db, await _tenant(db, ctx.tenant_id))
