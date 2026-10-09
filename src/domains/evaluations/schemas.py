from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EvaluationResultBase(BaseModel):
    session_id: UUID
    overall_score: Optional[int] = Field(
        default=None, description="0-100: the average of the 7 dimension scores"
    )
    summary: Optional[str] = None
    strengths: list[str] = Field(default=[], description="What the trainee did well")
    improvements: list[str] = Field(
        default=[], description="What the trainee did poorly"
    )
    missed_opportunities: list[str] = Field(
        default=[], description="Moments where a better response was possible"
    )
    recommendations: list[str] = Field(
        default=[], description="Concrete suggestions for next time"
    )


class EvaluationResultCreate(EvaluationResultBase):
    pass


class EvaluationResultUpdate(BaseModel):
    overall_score: Optional[int] = None
    summary: Optional[str] = None


class EvaluationResultResponse(EvaluationResultBase):
    id: UUID
    tenant_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DimensionScoreBase(BaseModel):
    evaluation_id: UUID
    dimension_key: Optional[str] = Field(
        default=None,
        description="accuracy | empathy | clarity | policy | resolution | "
        "de_escalation | efficiency (null on evaluations from before 0-100 scoring)",
    )
    dimension_name: str
    score: int = Field(description="0-100")
    rationale: str = Field(description="Why, with evidence from the conversation")


class DimensionScoreCreate(DimensionScoreBase):
    pass


class DimensionScoreUpdate(DimensionScoreBase):
    pass


class DimensionScoreResponse(DimensionScoreBase):
    id: UUID

    model_config = ConfigDict(from_attributes=True)


class RedFlagBase(BaseModel):
    evaluation_id: UUID
    reason: str
    description: str


class RedFlagCreate(RedFlagBase):
    pass


class RedFlagUpdate(RedFlagBase):
    pass


class RedFlagResponse(RedFlagBase):
    id: UUID

    model_config = ConfigDict(from_attributes=True)


class EvaluationResultDetailResponse(EvaluationResultResponse):
    dimension_scores: list[DimensionScoreResponse] = Field(
        default_factory=list
    )
    red_flags: list[RedFlagResponse] = Field(
        default_factory=list
    )