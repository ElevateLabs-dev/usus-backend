from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.core.training import SkillDimension, TrainingCategory
from src.domains.scenarios.models import CustomerPersona, DifficultyLevel


class ImportantInformation(BaseModel):
    label: str = Field(description="e.g. 'Refund policy'")
    content: str


class ScenarioBase(BaseModel):
    name: str
    description: str
    system_prompt: Optional[str] = None
    persona: CustomerPersona
    difficulty: DifficultyLevel
    category: Optional[TrainingCategory] = None
    skills: list[SkillDimension] = []
    estimated_minutes: int = 10
    customer_name: Optional[str] = None
    customer_personality: Optional[str] = None
    customer_emotion: Optional[str] = None
    customer_background: Optional[str] = None
    situation: Optional[str] = None
    customer_goal: Optional[str] = None
    trainee_objective: Optional[str] = None
    important_information: list[ImportantInformation] = []
    escalation_behavior: Optional[str] = None
    success_criteria: Optional[str] = None


class ScenarioCreate(ScenarioBase):
    pass


class ScenarioUpdate(ScenarioBase):
    pass


# ---------------------------------------------------------------------------
# Trainee-facing responses (never include the AI instructions, escalation
# rules or success criteria — those would give the scenario away)
# ---------------------------------------------------------------------------


class CategoryRef(BaseModel):
    id: TrainingCategory
    name: str


class SkillRef(BaseModel):
    id: SkillDimension
    name: str


class CategoryResponse(CategoryRef):
    description: str
    scenario_count: int = Field(description="Scenarios in this category for you")


class ScenarioProgress(BaseModel):
    """The signed-in user's own history with a scenario."""

    status: str = Field(
        description="'new' (never tried), 'in_progress' (a session is open) or "
        "'completed' (at least one evaluated session)"
    )
    attempts: int = Field(description="Sessions started for this scenario")
    best_score: Optional[int] = Field(description="Best overall score, 0-100")
    last_score: Optional[int] = Field(description="Most recent overall score, 0-100")


class ScenarioSummary(BaseModel):
    """A scenario in the browse list."""

    id: UUID
    name: str
    description: str
    category: Optional[CategoryRef]
    difficulty: DifficultyLevel
    persona: CustomerPersona
    skills: list[SkillRef] = Field(description="Skills this scenario tests")
    estimated_minutes: int
    progress: ScenarioProgress


class CustomerProfile(BaseModel):
    name: Optional[str]
    personality: Optional[str]
    emotion: Optional[str]
    background: Optional[str]


class ScenarioBrief(ScenarioSummary):
    """Everything the trainee reads before starting the role-play."""

    customer: CustomerProfile = Field(description="Who the customer is")
    situation: Optional[str] = Field(description="What happened")
    customer_goal: Optional[str] = Field(description="What the customer wants")
    trainee_objective: Optional[str] = Field(description="What the trainee must do")
    important_information: list[ImportantInformation] = Field(
        description="Policies and facts the trainee may use"
    )


class ScenarioResponse(ScenarioBase):
    """Full scenario including hidden fields (admin/seed use only)."""

    id: UUID
    tenant_id: UUID

    model_config = ConfigDict(from_attributes=True)
