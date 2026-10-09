"""Progress calculations from a user's evaluated sessions."""

import uuid
from collections import defaultdict
from datetime import datetime
from statistics import mean

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import UserRole
from src.core.training import (
    CATEGORY_INFO,
    SkillDimension,
    dimension_name,
)
from src.domains.evaluations.models import DimensionScore, EvaluationResult
from src.domains.progress.schemas import (
    CategoryProgress,
    DimensionProgress,
    ProgressReport,
    ScorePoint,
    TraineeSummary,
)
from src.domains.scenarios.models import Scenario
from src.domains.simulations.models import Session
from src.domains.users.models import User


def _avg(values: list[int]) -> int | None:
    return round(mean(values)) if values else None


async def build_report(
    db: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> ProgressReport:
    sessions_started = (
        await db.execute(
            select(func.count(Session.id)).where(
                Session.tenant_id == tenant_id, Session.user_id == user_id
            )
        )
    ).scalar_one()

    evaluated = (
        await db.execute(
            select(
                Session.id,
                Session.created_at,
                Session.ended_at,
                Scenario.name,
                Scenario.category,
                EvaluationResult.id,
                EvaluationResult.overall_score,
            )
            .join(Scenario, Scenario.id == Session.scenario_id)
            .join(EvaluationResult, EvaluationResult.session_id == Session.id)
            .where(
                Session.tenant_id == tenant_id,
                Session.user_id == user_id,
                EvaluationResult.overall_score.is_not(None),
            )
            .order_by(Session.created_at)
        )
    ).all()

    history = [
        ScorePoint(
            session_id=session_id,
            scenario_name=name,
            category=category,
            completed_at=ended_at or created_at,
            overall_score=score,
        )
        for session_id, created_at, ended_at, name, category, _, score in evaluated
    ]
    scores = [point.overall_score for point in history]
    practice_seconds = sum(
        (ended_at - created_at).total_seconds()
        for _, created_at, ended_at, *_ in evaluated
        if ended_at
    )

    score_change = None
    if len(scores) >= 2:
        window = min(3, len(scores) // 2)
        score_change = round(mean(scores[-window:]) - mean(scores[:window]))

    # Per-dimension scores in session order (only 0-100 evaluations have a key)
    eval_order = {row[5]: i for i, row in enumerate(evaluated)}
    by_dimension: dict[str, list[tuple[int, int]]] = defaultdict(list)
    if eval_order:
        dim_rows = await db.execute(
            select(
                DimensionScore.evaluation_id,
                DimensionScore.dimension_key,
                DimensionScore.score,
            ).where(
                DimensionScore.evaluation_id.in_(list(eval_order)),
                DimensionScore.dimension_key.is_not(None),
            )
        )
        for evaluation_id, key, score in dim_rows.all():
            by_dimension[key].append((eval_order[evaluation_id], score))

    dimensions = []
    for dimension in SkillDimension:
        points = [score for _, score in sorted(by_dimension.get(dimension.value, []))]
        if points:
            dimensions.append(
                DimensionProgress(
                    id=dimension,
                    name=dimension_name(dimension),
                    average=round(mean(points)),
                    latest=points[-1],
                    change=points[-1] - points[0],
                )
            )

    by_category: dict[str, list[int]] = defaultdict(list)
    for point in history:
        if point.category:
            by_category[point.category.value].append(point.overall_score)

    return ProgressReport(
        user_id=user_id,
        sessions_started=sessions_started,
        sessions_completed=len(history),
        total_practice_minutes=round(practice_seconds / 60),
        average_score=_avg(scores),
        best_score=max(scores) if scores else None,
        latest_score=scores[-1] if scores else None,
        score_change=score_change,
        improving=None if score_change is None else score_change > 0,
        score_history=history,
        dimensions=dimensions,
        categories=[
            CategoryProgress(
                id=category,
                name=name,
                sessions_completed=len(by_category.get(category.value, [])),
                average_score=_avg(by_category.get(category.value, [])),
            )
            for category, (name, _) in CATEGORY_INFO.items()
        ],
    )


async def team_overview(db: AsyncSession, tenant_id: uuid.UUID) -> list[TraineeSummary]:
    trainees = (
        (
            await db.execute(
                select(User)
                .where(User.tenant_id == tenant_id, User.role == UserRole.TRAINEE.value)
                .order_by(User.email)
            )
        )
        .scalars()
        .all()
    )

    rows = await db.execute(
        select(
            Session.user_id,
            Session.created_at,
            Session.ended_at,
            EvaluationResult.overall_score,
        )
        .outerjoin(EvaluationResult, EvaluationResult.session_id == Session.id)
        .where(Session.tenant_id == tenant_id)
        .order_by(Session.created_at)
    )
    scores: dict[uuid.UUID, list[int]] = defaultdict(list)
    last_active: dict[uuid.UUID, datetime] = {}
    for user_id, created_at, ended_at, score in rows.all():
        last_active[user_id] = ended_at or created_at
        if score is not None:
            scores[user_id].append(score)

    return [
        TraineeSummary(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            must_change_password=user.must_change_password,
            sessions_completed=len(scores.get(user.id, [])),
            average_score=_avg(scores.get(user.id, [])),
            latest_score=scores[user.id][-1] if scores.get(user.id) else None,
            last_active_at=last_active.get(user.id),
        )
        for user in trainees
    ]
