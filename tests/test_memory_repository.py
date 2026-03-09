import pytest
import uuid
from src.infrastructure.storage.memory import MemoryRepository
from src.domains.scenarios.models import Scenario, CustomerPersona, DifficultyLevel


class TestMemoryRepository:
    def test_save_and_get(self):
        repo = MemoryRepository[Scenario]()
        tenant_id = uuid.uuid4()
        scenario_id = uuid.uuid4()

        scenario = Scenario(
            id=scenario_id,
            tenant_id=tenant_id,
            name="Test Scenario",
            description="Test Desc",
            persona=CustomerPersona.FRIENDLY,
            difficulty=DifficultyLevel.BEGINNER,
        )

        repo.save(tenant_id, scenario)

        # Test retrieval
        retrieved = repo.get(tenant_id, scenario_id)
        assert retrieved is not None
        assert retrieved.name == "Test Scenario"

    def test_cross_tenant_isolation(self):
        repo = MemoryRepository[Scenario]()
        tenant_1 = uuid.uuid4()
        tenant_2 = uuid.uuid4()
        scenario_id = uuid.uuid4()

        scenario = Scenario(
            id=scenario_id,
            tenant_id=tenant_1,
            name="Tenant 1 Scenario",
            description="Desc",
            persona=CustomerPersona.FRIENDLY,
            difficulty=DifficultyLevel.BEGINNER,
        )

        repo.save(tenant_1, scenario)

        # Test retrieval wrong tenant
        retrieved = repo.get(tenant_2, scenario_id)
        assert retrieved is None

    def test_list_and_delete(self):
        repo = MemoryRepository[Scenario]()
        tenant_id = uuid.uuid4()

        s1 = Scenario(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            name="S1",
            description="D",
            persona=CustomerPersona.FRIENDLY,
            difficulty=DifficultyLevel.BEGINNER,
        )
        s2 = Scenario(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            name="S2",
            description="D",
            persona=CustomerPersona.FRUSTRATED,
            difficulty=DifficultyLevel.INTERMEDIATE,
        )

        repo.save(tenant_id, s1)
        repo.save(tenant_id, s2)

        items = repo.list_all(tenant_id)
        assert len(items) == 2

        repo.delete(tenant_id, s1.id)
        items_after_delete = repo.list_all(tenant_id)
        assert len(items_after_delete) == 1
        assert items_after_delete[0].id == s2.id
