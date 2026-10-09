from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import AuthContext, get_auth_context
from src.core.training import TrainingCategory
from src.domains.scenarios.crud import scenario as scenario_repo
from src.domains.scenarios.models import DifficultyLevel
from src.domains.scenarios.schemas import (
    CategoryResponse,
    ScenarioBrief,
    ScenarioSummary,
)
from src.domains.scenarios.service import ScenarioService

_scenario_service = ScenarioService(repository=scenario_repo)

router = APIRouter(
    prefix="/api/v1/scenarios",
    tags=["Scenarios"],
)

_AUTH_ERRORS: dict[int | str, dict] = {
    401: {"description": "Missing/invalid token, or no organization in the token"},
    403: {"description": "Password change required"},
}


def _tenant_of(ctx: AuthContext) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant context required",
        )
    return ctx.tenant_id


@router.get(
    "/categories",
    response_model=list[CategoryResponse],
    summary="List training categories",
    description=(
        "The training categories (De-escalation, Communication, Problem "
        "Resolution, Empathy, Policy & Compliance) with how many scenarios your "
        "organization has in each. Use the `id` to filter `GET /scenarios/`."
    ),
    responses=_AUTH_ERRORS,
)
async def list_categories(
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await _scenario_service.list_categories(db, _tenant_of(ctx))


@router.get(
    "/",
    response_model=list[ScenarioSummary],
    summary="Browse scenarios",
    description=(
        "Scenarios for your organization, ordered by category then difficulty "
        "(Beginner → Advanced). Each item includes **your own** progress: "
        "`status` (new / in_progress / completed), `attempts`, `best_score` and "
        "`last_score`."
    ),
    responses=_AUTH_ERRORS,
)
async def list_scenarios(
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    category: Annotated[
        TrainingCategory | None, Query(description="Only this training category")
    ] = None,
    difficulty: Annotated[
        DifficultyLevel | None, Query(description="Only this difficulty")
    ] = None,
):
    tenant_id = _tenant_of(ctx)
    scenarios = await _scenario_service.list_all_scenarios(
        db, tenant_id, category=category, difficulty=difficulty
    )
    progress = await _scenario_service.user_progress(db, tenant_id, ctx.user_id)
    return [_scenario_service.to_summary(s, progress.get(s.id)) for s in scenarios]


@router.get(
    "/{scenario_id}",
    response_model=ScenarioBrief,
    summary="Get a scenario brief",
    description=(
        "Everything the trainee reads before starting the role-play: who the "
        "customer is, what happened, what the customer wants, the trainee's "
        "objective, the skills being tested, and policies/facts they may use. "
        "Includes your own progress on this scenario."
    ),
    responses={**_AUTH_ERRORS, 404: {"description": "Scenario not found"}},
)
async def get_scenario_detail(
    scenario_id: UUID,
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    tenant_id = _tenant_of(ctx)
    scenario = await _scenario_service.get_scenario_by_id(
        db=db, tenant_id=tenant_id, scenario_id=scenario_id
    )
    if scenario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scenario not found.",
        )

    progress = await _scenario_service.user_progress(db, tenant_id, ctx.user_id)
    return _scenario_service.to_brief(scenario, progress.get(scenario.id))
