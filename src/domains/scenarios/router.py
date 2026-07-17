from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_current_tenant_id
from src.domains.scenarios.crud import scenario as scenario_repo
from src.domains.scenarios.schemas import ScenarioResponse
from src.domains.scenarios.service import ScenarioService

_scenario_service = ScenarioService(repository=scenario_repo)

router = APIRouter(
    prefix="/api/v1/scenarios",
    tags=["Scenarios"],
)


@router.get("/", response_model=list[ScenarioResponse])
async def list_scenarios(
    tenant_id: Annotated[UUID, Depends(get_current_tenant_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await _scenario_service.list_all_scenarios(db=db, tenant_id=tenant_id)


@router.get("/{scenario_id}", response_model=ScenarioResponse)
async def get_scenario_detail(
    scenario_id: UUID,
    tenant_id: Annotated[UUID, Depends(get_current_tenant_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    scenario = await _scenario_service.get_scenario_by_id(
        db=db, tenant_id=tenant_id, scenario_id=scenario_id
    )
    if scenario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scenario not found.",
        )

    return scenario
