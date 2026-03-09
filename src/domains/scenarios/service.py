import uuid
from typing import List

from src.infrastructure.storage.memory import MemoryRepository
from src.domains.scenarios.models import Scenario, CustomerPersona, DifficultyLevel

class ScenarioService:
    def __init__(self, repository: MemoryRepository[Scenario]):
        self.repository = repository

    def list_all_scenarios(self, tenant_id: uuid.UUID) -> List[Scenario]:
        return self.repository.list_all(tenant_id)

    def seed_defaults(self, tenant_id: uuid.UUID) -> List[Scenario]:
        existing = self.list_all_scenarios(tenant_id)
        if existing:
            return existing
        
        scenarios = [
            Scenario(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                name="SaaS Subscription Cancellation",
                description="The customer wants to cancel their SaaS subscription because they found a cheaper alternative.",
                persona=CustomerPersona.FRIENDLY,
                difficulty=DifficultyLevel.BEGINNER
            ),
            Scenario(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                name="Late Delivery Complaint",
                description="The customer is frustrated because their package is 3 days late and it was a birthday gift.",
                persona=CustomerPersona.FRUSTRATED,
                difficulty=DifficultyLevel.INTERMEDIATE
            ),
            Scenario(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                name="Double Billed Account",
                description="The customer was charged twice for their monthly bill and is extremely angry, threatening legal action.",
                persona=CustomerPersona.ANGRY,
                difficulty=DifficultyLevel.ADVANCED
            )
        ]
        
        for s in scenarios:
            self.repository.save(tenant_id, s)
            
        return scenarios
