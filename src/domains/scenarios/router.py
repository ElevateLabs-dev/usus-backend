from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
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
