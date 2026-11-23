from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import (
    AuthContext,
    UserRole,
    get_auth_context,
    require_roles,
)
from src.domains.metrics import service
from src.domains.metrics.models import Metric
from src.domains.metrics.schemas import MetricCreate, MetricRead, MetricUpdate

router = APIRouter(prefix="/api/v1/metrics", tags=["Metrics"])

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
_NAME_TAKEN = {409: {"description": "A metric with this name already exists"}}


def _tenant_of(ctx: AuthContext) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant context required",
        )
    return ctx.tenant_id


def _read(metric: Metric) -> MetricRead:
    return MetricRead(
        id=metric.id,
        key=metric.key,
        name=metric.name,
        description=metric.description,
        is_default=False,
    )


async def _own_metric(db: AsyncSession, ctx: AuthContext, metric_id: UUID) -> Metric:
    metric = await db.get(Metric, metric_id)
    if metric is None or metric.tenant_id != _tenant_of(ctx):
        raise HTTPException(status_code=404, detail="Metric not found")
    return metric


@router.get(
    "/",
    response_model=list[MetricRead],
    summary="List evaluation metrics",
    description=(
        "The 7 default metrics (`is_default: true`, cannot be changed) followed "
        "by your organization's own. Put the `key`s a scenario should be scored "
        "on in its `metrics`; an empty list means the 7 defaults."
    ),
)
async def list_metrics(
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await service.list_metrics(db, _tenant_of(ctx))


@router.post(
    "/",
    response_model=MetricRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a metric",
    description=(
        "**Company admin / manager only.** The `description` tells the "
        "evaluator what good looks like, so be specific."
    ),
    responses={**_EDITOR_ERRORS, **_NAME_TAKEN},
)
async def create_metric(
    body: MetricCreate,
    ctx: _Editor,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        metric = await service.create_metric(
            db, _tenant_of(ctx), body.name, body.description
        )
    except service.MetricNameTakenError:
        raise HTTPException(status_code=409, detail="A metric with this name exists")
    return _read(metric)


@router.patch(
    "/{metric_id}",
    response_model=MetricRead,
    summary="Edit a metric",
    description="**Company admin / manager only.** The `key` never changes.",
    responses={**_EDITOR_ERRORS, **_NAME_TAKEN, 404: {"description": "Not found"}},
)
async def update_metric(
    metric_id: UUID,
    body: MetricUpdate,
    ctx: _Editor,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    metric = await _own_metric(db, ctx, metric_id)
    try:
        metric = await service.update_metric(db, metric, body.name, body.description)
    except service.MetricNameTakenError:
        raise HTTPException(status_code=409, detail="A metric with this name exists")
    return _read(metric)


@router.delete(
    "/{metric_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a metric",
    description=(
        "**Company admin / manager only.** Also removes it from scenarios. "
        "Past scores on it are kept."
    ),
    responses={**_EDITOR_ERRORS, 404: {"description": "Not found"}},
)
async def delete_metric(
    metric_id: UUID,
    ctx: _Editor,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await service.delete_metric(db, await _own_metric(db, ctx, metric_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
