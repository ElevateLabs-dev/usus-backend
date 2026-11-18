"""Usage reports: how long sessions took and what they cost."""

import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.scenarios.models import Scenario
from src.domains.simulations.models import Session, has_activity
from src.domains.tenants.models import Tenant
from src.domains.usage.models import UsageRecord
from src.domains.usage.schemas import (
    OrganizationUsage,
    SessionUsage,
    UsageReport,
    UsageTotals,
)
from src.domains.users.models import User

# How many sessions the report lists.
SESSION_LIMIT = 200


def _cost_of(*purposes: str):
    return func.coalesce(
        func.sum(
            case((UsageRecord.purpose.in_(purposes), UsageRecord.cost_usd), else_=0)
        ),
        0,
    )


def _usage_by_session():
    return (
        select(
            UsageRecord.session_id.label("session_id"),
            func.coalesce(func.sum(UsageRecord.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(UsageRecord.output_tokens), 0).label(
                "output_tokens"
            ),
            func.coalesce(func.sum(UsageRecord.seconds), 0).label("voice_seconds"),
            _cost_of("conversation", "voice_conversation").label("conversation_cost"),
            _cost_of("evaluation").label("evaluation_cost"),
            _cost_of("voice_call").label("voice_cost"),
        )
        .where(UsageRecord.session_id.is_not(None))
        .group_by(UsageRecord.session_id)
        .subquery()
    )


def _as_utc(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _money(value) -> float:
    return round(float(Decimal(str(value or 0))), 6)


async def usage_report(
    db: AsyncSession, days: int, tenant_id: uuid.UUID | None = None
) -> UsageReport:
    """Sessions started in the last `days` days, for one organization or (with
    tenant_id None) the whole platform."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    usage = _usage_by_session()

    query = (
        select(Session, Tenant.name, User.full_name, User.email, Scenario.name, usage)
        .join(Tenant, Tenant.id == Session.tenant_id)
        .outerjoin(User, User.id == Session.user_id)
        .outerjoin(Scenario, Scenario.id == Session.scenario_id)
        .outerjoin(usage, usage.c.session_id == Session.id)
        .where(Session.created_at >= since, has_activity())
        .order_by(Session.created_at.desc())
    )
    if tenant_id is not None:
        query = query.where(Session.tenant_id == tenant_id)

    rows = (await db.execute(query)).all()

    sessions: list[SessionUsage] = []
    for row in rows:
        session: Session = row[0]
        started = _as_utc(session.created_at)
        ended = _as_utc(session.ended_at)
        conversation = _money(row.conversation_cost)
        evaluation = _money(row.evaluation_cost)
        voice = _money(row.voice_cost)
        sessions.append(
            SessionUsage(
                session_id=session.id,
                organization_id=session.tenant_id,
                organization_name=row[1],
                trainee_name=row[2],
                trainee_email=row[3],
                scenario_name=row[4],
                mode="voice" if session.voice_call_id else "text",
                status=session.status.value,
                started_at=started,
                ended_at=ended,
                duration_seconds=(
                    max(0, round((ended - started).total_seconds())) if ended else None
                ),
                voice_seconds=row.voice_seconds or 0,
                input_tokens=row.input_tokens or 0,
                output_tokens=row.output_tokens or 0,
                conversation_cost=conversation,
                evaluation_cost=evaluation,
                voice_cost=voice,
                total_cost=round(conversation + evaluation + voice, 6),
            )
        )

    ai_cost = sum(s.conversation_cost + s.evaluation_cost for s in sessions)
    voice_cost = sum(s.voice_cost for s in sessions)
    voice_sessions = sum(1 for s in sessions if s.mode == "voice")
    totals = UsageTotals(
        sessions=len(sessions),
        text_sessions=len(sessions) - voice_sessions,
        voice_sessions=voice_sessions,
        session_minutes=round(sum(s.duration_seconds or 0 for s in sessions) / 60, 1),
        voice_minutes=round(sum(s.voice_seconds for s in sessions) / 60, 1),
        input_tokens=sum(s.input_tokens for s in sessions),
        output_tokens=sum(s.output_tokens for s in sessions),
        ai_cost=round(ai_cost, 6),
        voice_cost=round(voice_cost, 6),
        total_cost=round(ai_cost + voice_cost, 6),
    )

    organizations: list[OrganizationUsage] = []
    if tenant_id is None:
        by_org: dict[uuid.UUID, list[SessionUsage]] = defaultdict(list)
        for item in sessions:
            by_org[item.organization_id].append(item)
        for org_id, items in by_org.items():
            org_ai = sum(s.conversation_cost + s.evaluation_cost for s in items)
            org_voice = sum(s.voice_cost for s in items)
            organizations.append(
                OrganizationUsage(
                    organization_id=org_id,
                    organization_name=items[0].organization_name,
                    sessions=len(items),
                    voice_minutes=round(sum(s.voice_seconds for s in items) / 60, 1),
                    ai_cost=round(org_ai, 6),
                    voice_cost=round(org_voice, 6),
                    total_cost=round(org_ai + org_voice, 6),
                )
            )
        organizations.sort(key=lambda org: org.total_cost, reverse=True)

    return UsageReport(
        days=days,
        since=since,
        totals=totals,
        organizations=organizations,
        sessions=sessions[:SESSION_LIMIT],
    )
