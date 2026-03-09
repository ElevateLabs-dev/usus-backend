from uuid import UUID
from typing import Optional
from pydantic import BaseModel


class EvaluationResultBase(BaseModel):
    session_id: UUID
    overall_score: Optional[int] = None
    summary: Optional[str] = None


class EvaluationResultCreate(EvaluationResultBase):
    pass


class EvaluationResultUpdate(BaseModel):
    overall_score: Optional[int] = None
    summary: Optional[str] = None


class EvaluationResultResponse(EvaluationResultBase):
    id: UUID
    tenant_id: UUID

    class Config:
        from_attributes = True


class DimensionScoreBase(BaseModel):
    evaluation_id: UUID
    dimension_name: str
    score: int
    rationale: str


class DimensionScoreCreate(DimensionScoreBase):
    pass


class DimensionScoreUpdate(DimensionScoreBase):
    pass


class DimensionScoreResponse(DimensionScoreBase):
    id: UUID

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True
