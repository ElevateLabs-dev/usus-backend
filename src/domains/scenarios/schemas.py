from datetime import datetime
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
        description="'new' (never tried), 'in_progress' (tried but not passed "
        "yet) or 'completed' (passed: best score 60 or more)"
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
    locked: bool = Field(
        default=False,
        description="True when the trainee has not unlocked this level yet",
    )
    locked_reason: Optional[str] = Field(
        default=None, description="What the trainee must do to unlock it"
    )


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


# ---------------------------------------------------------------------------
# Managing scenarios (company admins / managers) — includes the hidden fields
# ---------------------------------------------------------------------------


class ScenarioWrite(BaseModel):
    """Create a scenario. The AI customer is built from these fields."""

    name: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=10, description="One or two sentences")
    category: TrainingCategory
    difficulty: DifficultyLevel
    persona: CustomerPersona = Field(description="The customer's overall mood")
    skills: list[SkillDimension] = Field(
        default=[], max_length=7, description="Skills this scenario tests"
    )
    estimated_minutes: int = Field(default=10, ge=1, le=120)

    customer_name: Optional[str] = Field(default=None, max_length=255)
    customer_personality: Optional[str] = Field(default=None, max_length=255)
    customer_emotion: Optional[str] = Field(default=None, max_length=255)
    customer_background: Optional[str] = None
    situation: str = Field(min_length=10, description="What happened")
    customer_goal: Optional[str] = Field(
        default=None, description="What the customer wants"
    )
    trainee_objective: str = Field(
        min_length=10, description="What the trainee must do"
    )
    important_information: list[ImportantInformation] = Field(
        default=[], description="Policies and facts the trainee may use"
    )

    escalation_behavior: Optional[str] = Field(
        default=None,
        description="Hidden from trainees: how the customer reacts to poor handling",
    )
    success_criteria: Optional[str] = Field(
        default=None,
        description="Hidden from trainees: what good handling looks like "
        "(used by the evaluator)",
    )
    system_prompt: Optional[str] = Field(
        default=None,
        description="Hidden from trainees: optional hand-written AI customer "
        "instructions. Leave empty to build them from the fields above.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Failed Payment at Checkout",
                "description": "A customer's card was declined twice but their "
                "bank shows a pending charge.",
                "category": "problem_resolution",
                "difficulty": "intermediate",
                "persona": "frustrated",
                "skills": ["resolution", "accuracy", "clarity"],
                "estimated_minutes": 10,
                "customer_name": "Chidi",
                "customer_personality": "Careful with money, wants clear answers",
                "customer_emotion": "Worried",
                "customer_background": "First-time customer buying a laptop.",
                "situation": "Checkout failed twice, but the bank app shows a "
                "pending charge for the full amount.",
                "customer_goal": "To know whether they were charged and to "
                "complete the order.",
                "trainee_objective": "Reassure the customer, explain pending "
                "charges accurately, and help them complete the purchase.",
                "important_information": [
                    {
                        "label": "Pending charges",
                        "content": "Failed payments are released by the bank "
                        "within 3-5 business days.",
                    }
                ],
                "escalation_behavior": "Vague answers make the customer threaten "
                "to dispute the charge with their bank.",
                "success_criteria": "Explains the pending charge correctly, gives "
                "a timeframe, and offers a way to complete the order.",
            }
        }
    )


class ScenarioPatch(BaseModel):
    """Edit a scenario: send only the fields to change."""

    name: Optional[str] = Field(default=None, min_length=3, max_length=255)
    description: Optional[str] = Field(default=None, min_length=10)
    category: Optional[TrainingCategory] = None
    difficulty: Optional[DifficultyLevel] = None
    persona: Optional[CustomerPersona] = None
    skills: Optional[list[SkillDimension]] = Field(default=None, max_length=7)
    estimated_minutes: Optional[int] = Field(default=None, ge=1, le=120)
    customer_name: Optional[str] = Field(default=None, max_length=255)
    customer_personality: Optional[str] = Field(default=None, max_length=255)
    customer_emotion: Optional[str] = Field(default=None, max_length=255)
    customer_background: Optional[str] = None
    situation: Optional[str] = Field(default=None, min_length=10)
    customer_goal: Optional[str] = None
    trainee_objective: Optional[str] = Field(default=None, min_length=10)
    important_information: Optional[list[ImportantInformation]] = None
    escalation_behavior: Optional[str] = None
    success_criteria: Optional[str] = None
    system_prompt: Optional[str] = None
    is_archived: Optional[bool] = Field(
        default=None, description="false restores an archived scenario"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"difficulty": "advanced", "estimated_minutes": 15}
        }
    )


class ScenarioManage(ScenarioBase):
    """The full scenario as editors see it, including the hidden fields."""

    id: UUID
    tenant_id: UUID
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ScenarioResponse(ScenarioBase):
    """Full scenario including hidden fields (admin/seed use only)."""

    id: UUID
    tenant_id: UUID

    model_config = ConfigDict(from_attributes=True)
