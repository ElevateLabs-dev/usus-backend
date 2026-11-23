from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import AuthContext, UserRole, require_roles
from src.domains.teams import service
from src.domains.teams.models import Team
from src.domains.teams.schemas import (
    MemberIds,
    ScenarioIds,
    TeamCreate,
    TeamDetail,
    TeamRead,
    TeamUpdate,
)

router = APIRouter(prefix="/api/v1/teams", tags=["Teams"])

_Staff = Annotated[
    AuthContext,
    Depends(
        require_roles(UserRole.COMPANY_ADMIN, UserRole.MANAGER, UserRole.PLATFORM_ADMIN)
    ),
]
_ERRORS: dict[int | str, dict] = {
    401: {"description": "Missing/invalid token, or no organization in the token"},
    403: {"description": "Caller is not a company admin or manager"},
}
_NOT_FOUND = {404: {"description": "Team not found"}}
_NAME_TAKEN = {409: {"description": "A team with this name already exists"}}


def _tenant_of(ctx: AuthContext) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant context required",
        )
    return ctx.tenant_id


async def _team(db: AsyncSession, ctx: AuthContext, team_id: UUID) -> Team:
    team = await db.get(Team, team_id)
    if team is None or team.tenant_id != _tenant_of(ctx):
        raise HTTPException(status_code=404, detail="Team not found")
    return team


def _taken() -> HTTPException:
    return HTTPException(status_code=409, detail="A team with this name exists")


@router.get(
    "/",
    response_model=list[TeamRead],
    summary="List teams",
    responses=_ERRORS,
)
async def list_teams(ctx: _Staff, db: Annotated[AsyncSession, Depends(get_db)]):
    return await service.list_teams(db, _tenant_of(ctx))


@router.post(
    "/",
    response_model=TeamDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create a team",
    description=(
        "**Company admin / manager only.** Add trainees with "
        "`POST /teams/{id}/members`, or pick the team when inviting them "
        "(`team_ids`)."
    ),
    responses={**_ERRORS, **_NAME_TAKEN},
)
async def create_team(
    body: TeamCreate, ctx: _Staff, db: Annotated[AsyncSession, Depends(get_db)]
):
    try:
        team = await service.create_team(
            db, _tenant_of(ctx), body.name, body.description
        )
    except service.TeamNameTakenError:
        raise _taken()
    return await service.team_detail(db, team)


@router.get(
    "/{team_id}",
    response_model=TeamDetail,
    summary="Get a team with its members and scenarios",
    responses={**_ERRORS, **_NOT_FOUND},
)
async def get_team(
    team_id: UUID, ctx: _Staff, db: Annotated[AsyncSession, Depends(get_db)]
):
    return await service.team_detail(db, await _team(db, ctx, team_id))


@router.patch(
    "/{team_id}",
    response_model=TeamDetail,
    summary="Rename a team or change its description",
    responses={**_ERRORS, **_NOT_FOUND, **_NAME_TAKEN},
)
async def update_team(
    team_id: UUID,
    body: TeamUpdate,
    ctx: _Staff,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    team = await _team(db, ctx, team_id)
    try:
        team = await service.update_team(db, team, body.model_dump(exclude_unset=True))
    except service.TeamNameTakenError:
        raise _taken()
    return await service.team_detail(db, team)


@router.delete(
    "/{team_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a team",
    description=(
        "Users and scenarios are kept. Scenarios that were only assigned to this "
        "team become visible to everyone."
    ),
    responses={**_ERRORS, **_NOT_FOUND},
)
async def delete_team(
    team_id: UUID, ctx: _Staff, db: Annotated[AsyncSession, Depends(get_db)]
):
    await service.delete_team(db, await _team(db, ctx, team_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{team_id}/members",
    response_model=TeamDetail,
    summary="Add users to a team",
    description="Users already in the team are ignored. A user can be in many teams.",
    responses={**_ERRORS, **_NOT_FOUND, 422: {"description": "Unknown user"}},
)
async def add_members(
    team_id: UUID,
    body: MemberIds,
    ctx: _Staff,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    team = await _team(db, ctx, team_id)
    try:
        await service.add_users_to_team(db, team, body.user_ids)
    except service.UnknownIdsError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return await service.team_detail(db, team)


@router.delete(
    "/{team_id}/members/{user_id}",
    response_model=TeamDetail,
    summary="Remove a user from a team",
    responses={**_ERRORS, 404: {"description": "Team or member not found"}},
)
async def remove_member(
    team_id: UUID,
    user_id: UUID,
    ctx: _Staff,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    team = await _team(db, ctx, team_id)
    if not await service.remove_member(db, team, user_id):
        raise HTTPException(status_code=404, detail="Not a member of this team")
    return await service.team_detail(db, team)


@router.put(
    "/{team_id}/scenarios",
    response_model=TeamDetail,
    summary="Set the team's scenarios",
    description=(
        "Replaces the team's scenarios. A scenario assigned to one or more teams "
        "is only shown to those teams' trainees; a scenario with no team is "
        "shown to everyone."
    ),
    responses={**_ERRORS, **_NOT_FOUND, 422: {"description": "Unknown scenario"}},
)
async def set_scenarios(
    team_id: UUID,
    body: ScenarioIds,
    ctx: _Staff,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    team = await _team(db, ctx, team_id)
    try:
        await service.set_scenarios(db, team, body.scenario_ids)
    except service.UnknownIdsError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return await service.team_detail(db, team)
