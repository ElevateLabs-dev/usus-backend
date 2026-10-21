from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import AsyncSessionLocal, get_db
from src.core.dependencies import (
    AuthContext,
    UserRole,
    get_auth_context,
    require_roles,
)
from src.core.training import TrainingCategory
from src.domains.notifications.service import notify_scenario_added
from src.domains.scenarios.crud import scenario as scenario_repo
from src.domains.scenarios.models import DifficultyLevel, Scenario
from src.domains.scenarios.schemas import (
    CategoryResponse,
    ScenarioBrief,
    ScenarioManage,
    ScenarioPatch,
    ScenarioSummary,
    ScenarioWrite,
)
from src.domains.scenarios.service import ScenarioNameTakenError, ScenarioService

_scenario_service = ScenarioService(repository=scenario_repo)

router = APIRouter(
    prefix="/api/v1/scenarios",
    tags=["Scenarios"],
)

# Session factory for background notifications (swapped out in tests).
_session_factory = AsyncSessionLocal

_AUTH_ERRORS: dict[int | str, dict] = {
    401: {"description": "Missing/invalid token, or no organization in the token"},
    403: {"description": "Password change required"},
}


_Editor = Annotated[
    AuthContext,
    Depends(
        require_roles(UserRole.COMPANY_ADMIN, UserRole.MANAGER, UserRole.PLATFORM_ADMIN)
    ),
]

_EDITOR_ERRORS: dict[int | str, dict] = {
    401: {"description": "Missing/invalid token, or no organization in the token"},
    403: {"description": "Caller is not a company admin or manager"},
}
_NAME_TAKEN = {
    409: {"description": "Your organization already has a scenario with this name"}
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
    "/manage",
    response_model=list[ScenarioManage],
    summary="List scenarios for editing (includes archived)",
    description=(
        "**Company admin / manager only.** Every scenario in your organization "
        "with all fields, including archived ones (`is_archived: true`)."
    ),
    responses=_EDITOR_ERRORS,
)
async def list_scenarios_for_editing(
    ctx: _Editor,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await _scenario_service.list_all_scenarios(
        db, _tenant_of(ctx), include_archived=True
    )


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
    if scenario is None or scenario.is_archived:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scenario not found.",
        )

    progress = await _scenario_service.user_progress(db, tenant_id, ctx.user_id)
    return _scenario_service.to_brief(scenario, progress.get(scenario.id))


# ---------------------------------------------------------------------------
# Managing scenarios (company admins / managers)
# ---------------------------------------------------------------------------


async def _editable_scenario(
    db: AsyncSession, ctx: AuthContext, scenario_id: UUID
) -> Scenario:
    scenario = await _scenario_service.get_scenario_by_id(
        db=db, tenant_id=_tenant_of(ctx), scenario_id=scenario_id
    )
    if scenario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found."
        )
    return scenario


@router.post(
    "/",
    response_model=ScenarioManage,
    status_code=status.HTTP_201_CREATED,
    summary="Create a scenario",
    description=(
        "**Company admin / manager only.** Adds a scenario to your organization. "
        "The AI customer is generated from the brief (customer, situation, goal, "
        "escalation behaviour), so no prompt writing is needed; `system_prompt` "
        "is an optional override.\n\n"
        "`escalation_behavior`, `success_criteria` and `system_prompt` are never "
        "shown to trainees. `success_criteria` and `important_information` are "
        "used by the evaluator."
    ),
    responses={**_EDITOR_ERRORS, **_NAME_TAKEN},
)
async def create_scenario(
    body: ScenarioWrite,
    ctx: _Editor,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    try:
        scenario = await _scenario_service.create_scenario(db, _tenant_of(ctx), body)
    except ScenarioNameTakenError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A scenario with this name already exists",
        )
    # Sent after the response, so a failure there can't affect it.
    background_tasks.add_task(
        notify_scenario_added,
        scenario.id,
        scenario.tenant_id,
        scenario.name,
        _session_factory,
    )
    return scenario


@router.get(
    "/{scenario_id}/manage",
    response_model=ScenarioManage,
    summary="Get a scenario for editing (includes hidden fields)",
    description=(
        "**Company admin / manager only.** The complete scenario, including the "
        "fields trainees never see and whether it is archived."
    ),
    responses={**_EDITOR_ERRORS, 404: {"description": "Scenario not found"}},
)
async def get_scenario_for_editing(
    scenario_id: UUID,
    ctx: _Editor,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await _editable_scenario(db, ctx, scenario_id)


@router.patch(
    "/{scenario_id}",
    response_model=ScenarioManage,
    summary="Edit a scenario",
    description=(
        "**Company admin / manager only.** Send only the fields to change. "
        "Changes apply to new sessions; sessions already started keep the "
        "customer they began with. Set `is_archived` to false to restore an "
        "archived scenario."
    ),
    responses={
        **_EDITOR_ERRORS,
        **_NAME_TAKEN,
        404: {"description": "Scenario not found"},
    },
)
async def update_scenario(
    scenario_id: UUID,
    body: ScenarioPatch,
    ctx: _Editor,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    scenario = await _editable_scenario(db, ctx, scenario_id)
    try:
        return await _scenario_service.update_scenario(db, scenario, body)
    except ScenarioNameTakenError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A scenario with this name already exists",
        )


@router.delete(
    "/{scenario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Archive a scenario",
    description=(
        "**Company admin / manager only.** Hides the scenario from trainees and "
        "stops new sessions for it. Nothing is deleted: past sessions, scores and "
        "progress are kept. Restore it with `PATCH` and `is_archived: false`."
    ),
    responses={**_EDITOR_ERRORS, 404: {"description": "Scenario not found"}},
)
async def archive_scenario(
    scenario_id: UUID,
    ctx: _Editor,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    scenario = await _editable_scenario(db, ctx, scenario_id)
    await _scenario_service.update_scenario(
        db, scenario, ScenarioPatch(is_archived=True)
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
