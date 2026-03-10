from uuid import UUID
from typing import Optional
from pydantic import BaseModel, ConfigDict
from src.domains.scenarios.models import CustomerPersona, DifficultyLevel


class ScenarioBase(BaseModel):
    name: str
    description: str
    system_prompt: Optional[str] = None
    persona: CustomerPersona
    difficulty: DifficultyLevel


class ScenarioCreate(ScenarioBase):
    pass


class ScenarioUpdate(ScenarioBase):
    pass


class ScenarioResponse(ScenarioBase):
    id: UUID
    tenant_id: UUID

    model_config = ConfigDict(from_attributes=True)
