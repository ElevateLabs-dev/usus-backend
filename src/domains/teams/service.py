"""
Teams. Trainees see scenarios that have no team (for everyone) plus the ones
assigned to their teams; staff see every scenario.
"""

import uuid
from typing import Iterable, Sequence

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.scenarios.models import Scenario
from src.domains.teams.models import Team, TeamMember, TeamScenario
from src.domains.teams.schemas import (
    TeamDetail,
    TeamMemberRead,
    TeamRead,
    TeamScenarioRead,
)
from src.domains.users.models import User


class TeamNameTakenError(Exception):
    pass


class UnknownIdsError(ValueError):
    pass


def visible_to(user_id: uuid.UUID):
    """Filter for the scenarios a trainee may see."""
    has_team = select(TeamScenario.scenario_id)
    their_teams = (
        select(TeamScenario.scenario_id)
        .join(TeamMember, TeamMember.team_id == TeamScenario.team_id)
        .where(TeamMember.user_id == user_id)
    )
    return or_(Scenario.id.not_in(has_team), Scenario.id.in_(their_teams))


async def can_see(db: AsyncSession, scenario_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    found = await db.execute(
        select(Scenario.id).where(Scenario.id == scenario_id, visible_to(user_id))
    )
    return found.first() is not None


async def _counts(db: AsyncSession, model, ids: list[uuid.UUID]) -> dict:
    if not ids:
        return {}
    rows = await db.execute(
        select(model.team_id, func.count(model.id))
        .where(model.team_id.in_(ids))
        .group_by(model.team_id)
    )
    return dict(rows.all())


async def list_teams(db: AsyncSession, tenant_id: uuid.UUID) -> list[TeamRead]:
    teams = (
        (
            await db.execute(
                select(Team).where(Team.tenant_id == tenant_id).order_by(Team.name)
            )
        )
        .scalars()
        .all()
    )
    ids = [t.id for t in teams]
    members = await _counts(db, TeamMember, ids)
    scenarios = await _counts(db, TeamScenario, ids)
    return [
        TeamRead(
            id=t.id,
            name=t.name,
            description=t.description,
            member_count=members.get(t.id, 0),
            scenario_count=scenarios.get(t.id, 0),
            created_at=t.created_at,
        )
        for t in teams
    ]


async def team_detail(db: AsyncSession, team: Team) -> TeamDetail:
    members = (
        await db.execute(
            select(User)
            .join(TeamMember, TeamMember.user_id == User.id)
            .where(TeamMember.team_id == team.id)
            .order_by(User.full_name, User.email)
        )
    ).scalars()
    scenarios = (
        await db.execute(
            select(Scenario.id, Scenario.name)
            .join(TeamScenario, TeamScenario.scenario_id == Scenario.id)
            .where(TeamScenario.team_id == team.id)
            .order_by(Scenario.name)
        )
    ).all()
    member_list = [
        TeamMemberRead(id=u.id, email=u.email, full_name=u.full_name, role=u.role)
        for u in members
    ]
    return TeamDetail(
        id=team.id,
        name=team.name,
        description=team.description,
        member_count=len(member_list),
        scenario_count=len(scenarios),
        created_at=team.created_at,
        members=member_list,
        scenarios=[TeamScenarioRead(id=i, name=n) for i, n in scenarios],
    )


async def _name_taken(
    db: AsyncSession, tenant_id: uuid.UUID, name: str, exclude: uuid.UUID | None
) -> bool:
    query = select(Team.id).where(
        Team.tenant_id == tenant_id, func.lower(Team.name) == name.lower()
    )
    if exclude is not None:
        query = query.where(Team.id != exclude)
    return (await db.execute(query)).first() is not None


async def create_team(
    db: AsyncSession, tenant_id: uuid.UUID, name: str, description: str | None
) -> Team:
    if await _name_taken(db, tenant_id, name, None):
        raise TeamNameTakenError(name)
    team = Team(tenant_id=tenant_id, name=name, description=description)
    db.add(team)
    await db.commit()
    await db.refresh(team)
    return team


async def update_team(db: AsyncSession, team: Team, changes: dict) -> Team:
    name = changes.get("name")
    if name and name != team.name:
        if await _name_taken(db, team.tenant_id, name, team.id):
            raise TeamNameTakenError(name)
        team.name = name
    if "description" in changes:
        team.description = changes["description"]
    await db.commit()
    await db.refresh(team)
    return team


async def delete_team(db: AsyncSession, team: Team) -> None:
    await db.execute(delete(TeamMember).where(TeamMember.team_id == team.id))
    await db.execute(delete(TeamScenario).where(TeamScenario.team_id == team.id))
    await db.delete(team)
    await db.commit()


async def _check_ids(
    db: AsyncSession, tenant_id: uuid.UUID, model, ids: Iterable[uuid.UUID], what: str
) -> list[uuid.UUID]:
    unique = list(dict.fromkeys(ids))
    if not unique:
        return []
    found = set(
        (
            await db.execute(
                select(model.id).where(
                    model.id.in_(unique), model.tenant_id == tenant_id
                )
            )
        ).scalars()
    )
    missing = [str(i) for i in unique if i not in found]
    if missing:
        raise UnknownIdsError(f"Unknown {what}: {', '.join(missing)}")
    return unique


async def check_team_ids(
    db: AsyncSession, tenant_id: uuid.UUID, ids: Iterable[uuid.UUID]
) -> list[uuid.UUID]:
    """Raises UnknownIdsError if a team is not in the organization."""
    return await _check_ids(db, tenant_id, Team, ids, "team(s)")


async def add_members(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    team_ids: Sequence[uuid.UUID],
    user_ids: Sequence[uuid.UUID],
) -> None:
    """Add users to teams; existing memberships are left as they are."""
    if not team_ids or not user_ids:
        return
    existing = set(
        (
            await db.execute(
                select(TeamMember.team_id, TeamMember.user_id).where(
                    TeamMember.team_id.in_(team_ids), TeamMember.user_id.in_(user_ids)
                )
            )
        ).all()
    )
    db.add_all(
        TeamMember(tenant_id=tenant_id, team_id=team_id, user_id=user_id)
        for team_id in team_ids
        for user_id in user_ids
        if (team_id, user_id) not in existing
    )
    await db.commit()


async def add_users_to_team(
    db: AsyncSession, team: Team, user_ids: Iterable[uuid.UUID]
) -> None:
    ids = await _check_ids(db, team.tenant_id, User, user_ids, "user(s)")
    await add_members(db, team.tenant_id, [team.id], ids)


async def remove_member(db: AsyncSession, team: Team, user_id: uuid.UUID) -> bool:
    result = await db.execute(
        delete(TeamMember).where(
            TeamMember.team_id == team.id, TeamMember.user_id == user_id
        )
    )
    await db.commit()
    return result.rowcount > 0


async def set_scenarios(
    db: AsyncSession, team: Team, scenario_ids: Iterable[uuid.UUID]
) -> None:
    ids = await _check_ids(db, team.tenant_id, Scenario, scenario_ids, "scenario(s)")
    await db.execute(delete(TeamScenario).where(TeamScenario.team_id == team.id))
    db.add_all(
        TeamScenario(tenant_id=team.tenant_id, team_id=team.id, scenario_id=i)
        for i in ids
    )
    await db.commit()


async def team_names(db: AsyncSession, user_id: uuid.UUID) -> list[str]:
    rows = await db.execute(
        select(Team.name)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == user_id)
        .order_by(Team.name)
    )
    return list(rows.scalars())
