import uuid
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from src.domains.scenarios.models import Scenario, CustomerPersona, DifficultyLevel
from src.domains.scenarios.schemas import ScenarioCreate
from src.domains.scenarios.crud import CRUDScenario

class ScenarioService:
    def __init__(self, repository: CRUDScenario):
        self.repository = repository

    async def list_all_scenarios(self, db: AsyncSession, tenant_id: uuid.UUID) -> Sequence[Scenario]:
        return await self.repository.get_multi(db=db, tenant_id=tenant_id)

    async def seed_defaults(self, db: AsyncSession, tenant_id: uuid.UUID) -> Sequence[Scenario]:
        existing = await self.list_all_scenarios(db, tenant_id)
        if existing:
            return existing
        
        scenarios_to_create = [
            ScenarioCreate(
                name="SaaS Subscription Cancellation",
                description="The customer wants to cancel their SaaS subscription because they found a cheaper alternative.",
                persona=CustomerPersona.FRIENDLY,
                difficulty=DifficultyLevel.BEGINNER
            ),
            ScenarioCreate(
                name="Late Delivery Complaint",
                description="The customer is frustrated because their package is 3 days late and it was a birthday gift.",
                persona=CustomerPersona.FRUSTRATED,
                difficulty=DifficultyLevel.INTERMEDIATE
            ),
            ScenarioCreate(
                name="Double Billed Account",
                description="The customer was charged twice for their monthly bill and is extremely angry, threatening legal action.",
                persona=CustomerPersona.ANGRY,
                difficulty=DifficultyLevel.ADVANCED
            )
        ]
        
        created = []
        for s_in in scenarios_to_create:
            s_obj = await self.repository.create(db=db, obj_in=s_in, tenant_id=tenant_id)
            created.append(s_obj)
            
        return created
