from uuid import UUID
from typing import Annotated
from fastapi import APIRouter, Depends

from src.core.dependencies import AuthContext, UserRole, require_roles
from src.domains.evaluations.tasks import generate_evaluation_report

# initialize router
router = APIRouter(
    prefix="/api/v1/evaluations",
    tags=["Evaluations"],
)


@router.post(
    "/{simulation_id}/generate",
    summary="Trigger evaluation generation (Manager+)",
)
async def trigger_evaluation(
    simulation_id: str,
    ctx: Annotated[
        AuthContext,
        Depends(
            require_roles(
                UserRole.MANAGER, UserRole.COMPANY_ADMIN, UserRole.PLATFORM_ADMIN
            )
        ),
    ],
):
    task = generate_evaluation_report.delay(simulation_id, ctx.tenant_id)  # type: ignore[attr-defined]
    return {"task_id": task.id, "status": "processing"}
