from uuid import UUID
from typing import Annotated
from fastapi import APIRouter, Depends

from src.core.dependencies import get_current_tenant_id
from src.domains.evaluations.tasks import generate_evaluation_report

# initialize router
router = APIRouter(
    prefix="/api/v1/evaluations",
    tags=["Evaluations"],
)


@router.post("/{simulation_id}/generate")
async def trigger_evaluation(
    simulation_id: str, tenant_id: Annotated[UUID, Depends(get_current_tenant_id)]
):
    task = generate_evaluation_report.delay(simulation_id, tenant_id)  # type: ignore[attr-defined]
    return {"task_id": task.id, "status": "processing"}
