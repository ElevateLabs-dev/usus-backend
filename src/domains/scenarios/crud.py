from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.core.base_crud import CRUDBase
from src.domains.scenarios.models import Scenario
from src.domains.scenarios.schemas import ScenarioCreate, ScenarioUpdate


class CRUDScenario(CRUDBase[Scenario, ScenarioCreate, ScenarioUpdate]):
    async def get_by_name(
        self, db: AsyncSession, tenant_id: UUID, name: str
    ) -> Scenario | None:
        query = select(self.model).where(
            self.model.tenant_id == tenant_id, self.model.name == name
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()


scenario = CRUDScenario(Scenario)
