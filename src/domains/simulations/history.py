"""Read-side queries for a user's training history."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.training import category_name
from src.domains.evaluations.crud import evaluation_result as eval_result_repo
from src.domains.evaluations.models import EvaluationResult
from src.domains.scenarios.models import Scenario
from src.domains.scenarios.schemas import CategoryRef
from src.domains.simulations.models import Message, MessageRole, Session, SessionStatus
from src.domains.simulations.schemas import (
    HistoryItem,
    HistoryPage,
    HistoryScenario,
    SessionDetail,
    TranscriptMessage,
)


def _history_query(tenant_id: uuid.UUID, user_id: uuid.UUID):
    message_count = (
        select(func.count(Message.id))
        .where(Message.session_id == Session.id, Message.role != MessageRole.SYSTEM)
        .correlate(Session)
        .scalar_subquery()
    )
    return (
        select(Session, Scenario, EvaluationResult.overall_score, message_count)
        .join(Scenario, Scenario.id == Session.scenario_id)
        .outerjoin(EvaluationResult, EvaluationResult.session_id == Session.id)
        .where(Session.tenant_id == tenant_id, Session.user_id == user_id)
    )


def _to_item(session: Session, scenario: Scenario, score, count) -> HistoryItem:
    duration = (
        int((session.ended_at - session.created_at).total_seconds())
        if session.ended_at and session.created_at
        else None
    )
    return HistoryItem(
        id=session.id,
        scenario=HistoryScenario(
            id=scenario.id,
            name=scenario.name,
            category=CategoryRef(
                id=scenario.category, name=category_name(scenario.category)
            )
            if scenario.category
            else None,
            difficulty=scenario.difficulty,
        ),
        status=session.status,
        started_at=session.created_at,
        ended_at=session.ended_at,
        duration_seconds=duration,
        overall_score=score,
        message_count=count or 0,
    )


async def list_history(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    scenario_id: uuid.UUID | None = None,
    status: SessionStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> HistoryPage:
    query = _history_query(tenant_id, user_id)
    count_query = select(func.count(Session.id)).where(
        Session.tenant_id == tenant_id, Session.user_id == user_id
    )
    if scenario_id is not None:
        query = query.where(Session.scenario_id == scenario_id)
        count_query = count_query.where(Session.scenario_id == scenario_id)
    if status is not None:
        query = query.where(Session.status == status)
        count_query = count_query.where(Session.status == status)

    rows = await db.execute(
        query.order_by(Session.created_at.desc()).limit(limit).offset(offset)
    )
    total = (await db.execute(count_query)).scalar_one()
    return HistoryPage(items=[_to_item(*row) for row in rows.all()], total=total)


async def get_session_detail(
    db: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID, session_id: uuid.UUID
) -> SessionDetail | None:
    row = (
        await db.execute(
            _history_query(tenant_id, user_id).where(Session.id == session_id)
        )
    ).first()
    if row is None:
        return None

    messages = (
        (
            await db.execute(
                select(Message)
                .where(
                    Message.tenant_id == tenant_id,
                    Message.session_id == session_id,
                    Message.role != MessageRole.SYSTEM,
                )
                .order_by(Message.created_at)
            )
        )
        .scalars()
        .all()
    )
    evaluation = await eval_result_repo.get_by_session_with_details(
        db=db, tenant_id=tenant_id, session_id=session_id
    )
    return SessionDetail(
        **_to_item(*row).model_dump(),
        messages=[TranscriptMessage.model_validate(m) for m in messages],
        evaluation=evaluation,
    )
