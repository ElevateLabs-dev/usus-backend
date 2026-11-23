"""
Evaluation metrics: the 7 defaults every company has, plus its own.

A scenario lists the metric keys it is scored on (`Scenario.metrics`); an
empty list means the 7 defaults.
"""

import re
import uuid
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.training import DIMENSION_INFO, SkillDimension
from src.domains.metrics.models import Metric
from src.domains.metrics.schemas import MetricRead
from src.domains.scenarios.models import Scenario

DEFAULT_KEYS = [d.value for d in SkillDimension]


@dataclass(frozen=True)
class MetricSpec:
    """A metric as the evaluator uses it."""

    key: str
    name: str
    description: str
    is_default: bool


DEFAULT_METRICS = [
    MetricSpec(key=d.value, name=name, description=description, is_default=True)
    for d, (name, description) in DIMENSION_INFO.items()
]


class MetricNameTakenError(Exception):
    pass


class UnknownMetricError(ValueError):
    pass


async def custom_metrics(db: AsyncSession, tenant_id: uuid.UUID) -> list[Metric]:
    result = await db.execute(
        select(Metric).where(Metric.tenant_id == tenant_id).order_by(Metric.name)
    )
    return list(result.scalars().all())


async def all_specs(db: AsyncSession, tenant_id: uuid.UUID) -> list[MetricSpec]:
    """Defaults first, then the company's own, by name."""
    return DEFAULT_METRICS + [
        MetricSpec(m.key, m.name, m.description, False)
        for m in await custom_metrics(db, tenant_id)
    ]


async def list_metrics(db: AsyncSession, tenant_id: uuid.UUID) -> list[MetricRead]:
    reads = [
        MetricRead(
            id=None,
            key=m.key,
            name=m.name,
            description=m.description,
            is_default=True,
        )
        for m in DEFAULT_METRICS
    ]
    for m in await custom_metrics(db, tenant_id):
        reads.append(
            MetricRead(
                id=m.id,
                key=m.key,
                name=m.name,
                description=m.description,
                is_default=False,
            )
        )
    return reads


async def metric_names(db: AsyncSession, tenant_id: uuid.UUID) -> dict[str, str]:
    return {m.key: m.name for m in await all_specs(db, tenant_id)}


async def for_scenario(
    db: AsyncSession, tenant_id: uuid.UUID, scenario: Scenario | None
) -> list[MetricSpec]:
    """
    The metrics a scenario is scored on, in display order. Falls back to the
    defaults if none are set (or all chosen ones were deleted).
    """
    chosen = set(scenario.metrics or []) if scenario else set()
    if not chosen:
        return list(DEFAULT_METRICS)
    specs = [m for m in await all_specs(db, tenant_id) if m.key in chosen]
    return specs or list(DEFAULT_METRICS)


async def check_keys(
    db: AsyncSession, tenant_id: uuid.UUID, keys: Iterable[str]
) -> list[str]:
    """The keys without duplicates; raises UnknownMetricError for unknown ones."""
    known = set(await metric_names(db, tenant_id))
    unique = list(dict.fromkeys(keys))
    unknown = [k for k in unique if k not in known]
    if unknown:
        raise UnknownMetricError(
            f"Unknown metric(s): {', '.join(unknown)}. See GET /metrics."
        )
    return unique


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug[:40] or "metric"


async def _name_taken(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    name: str,
    exclude: uuid.UUID | None = None,
) -> bool:
    if name.lower() in {m.name.lower() for m in DEFAULT_METRICS}:
        return True
    query = select(Metric.id).where(
        Metric.tenant_id == tenant_id, func.lower(Metric.name) == name.lower()
    )
    if exclude is not None:
        query = query.where(Metric.id != exclude)
    return (await db.execute(query)).first() is not None


async def create_metric(
    db: AsyncSession, tenant_id: uuid.UUID, name: str, description: str
) -> Metric:
    if await _name_taken(db, tenant_id, name):
        raise MetricNameTakenError(name)
    used = set(DEFAULT_KEYS) | {
        key
        for key in (
            await db.execute(select(Metric.key).where(Metric.tenant_id == tenant_id))
        ).scalars()
    }
    key = base = _slug(name)
    n = 2
    while key in used:
        key = f"{base}_{n}"
        n += 1
    metric = Metric(tenant_id=tenant_id, key=key, name=name, description=description)
    db.add(metric)
    await db.commit()
    await db.refresh(metric)
    return metric


async def update_metric(
    db: AsyncSession, metric: Metric, name: str | None, description: str | None
) -> Metric:
    if name and name != metric.name:
        if await _name_taken(db, metric.tenant_id, name, exclude=metric.id):
            raise MetricNameTakenError(name)
        metric.name = name
    if description:
        metric.description = description
    await db.commit()
    await db.refresh(metric)
    return metric


async def delete_metric(db: AsyncSession, metric: Metric) -> None:
    """Removes it from every scenario too. Past scores keep their name."""
    scenarios = (
        await db.execute(select(Scenario).where(Scenario.tenant_id == metric.tenant_id))
    ).scalars()
    for scenario in scenarios:
        if metric.key in (scenario.metrics or []):
            scenario.metrics = [k for k in scenario.metrics if k != metric.key]
    await db.delete(metric)
    await db.commit()
