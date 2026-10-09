from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.core.training import SkillDimension, TrainingCategory


class ScorePoint(BaseModel):
    session_id: UUID
    scenario_name: str
    category: TrainingCategory | None
    completed_at: datetime
    overall_score: int


class DimensionProgress(BaseModel):
    id: SkillDimension
    name: str
    average: int = Field(description="Average across all evaluated sessions, 0-100")
    latest: int = Field(description="Score in the most recent session")
    change: int = Field(description="Latest minus first score (positive = improving)")


class CategoryProgress(BaseModel):
    id: TrainingCategory
    name: str
    sessions_completed: int
    average_score: int | None


class ProgressReport(BaseModel):
    user_id: UUID
    sessions_started: int
    sessions_completed: int = Field(description="Sessions that were evaluated")
    total_practice_minutes: int
    average_score: int | None = Field(description="0-100; null before any evaluation")
    best_score: int | None
    latest_score: int | None
    score_change: int | None = Field(
        description="Average of the last 3 scores minus the first 3 (null with "
        "fewer than 2 evaluated sessions). Positive = improving."
    )
    improving: bool | None
    score_history: list[ScorePoint] = Field(description="Oldest first, for a chart")
    dimensions: list[DimensionProgress] = Field(
        description="The 7 dimensions (empty before any evaluation)"
    )
    categories: list[CategoryProgress]


class TraineeSummary(BaseModel):
    user_id: UUID
    email: str
    full_name: str | None
    must_change_password: bool = Field(description="True = has not signed in yet")
    sessions_completed: int
    average_score: int | None
    latest_score: int | None
    last_active_at: datetime | None
