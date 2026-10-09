from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.domains.scenarios.models import DifficultyLevel
from src.domains.simulations.models import (
    MessageRole,
    SessionStatus,
)

# ---------------------------------------------------------------------------
# Session schemas
# ---------------------------------------------------------------------------


class SessionBase(BaseModel):
    scenario_id: UUID
    status: SessionStatus = SessionStatus.NOT_STARTED


class SessionCreate(SessionBase):
    user_id: UUID | None = None


class SessionUpdate(BaseModel):
    status: SessionStatus | None = None
    ended_at: datetime | None = None


class SessionResponse(SessionBase):
    id: UUID
    tenant_id: UUID
    user_id: UUID | None = None
    created_at: datetime
    ended_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Message schemas
# ---------------------------------------------------------------------------


class MessageBase(BaseModel):
    session_id: UUID
    role: MessageRole
    content: str


class MessageCreate(MessageBase):
    pass


class MessageUpdate(MessageBase):
    pass


class MessageResponse(MessageBase):
    id: UUID
    tenant_id: UUID

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class StartSessionRequest(BaseModel):
    scenario_id: UUID


class SendMessageRequest(BaseModel):
    content: str


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class SendMessageResponse(BaseModel):
    user_message: MessageResponse
    ai_reply: MessageResponse


# ---------------------------------------------------------------------------
# History schemas
# ---------------------------------------------------------------------------


class HistoryScenario(BaseModel):
    id: UUID
    name: str
    category: "CategoryRef | None"
    difficulty: DifficultyLevel


class HistoryItem(BaseModel):
    """One of the user's sessions in their training history."""

    id: UUID
    scenario: HistoryScenario
    status: SessionStatus
    started_at: datetime
    ended_at: datetime | None
    duration_seconds: int | None = Field(
        description="ended_at - started_at; null while the session is open"
    )
    overall_score: int | None = Field(description="0-100; null until evaluated")
    message_count: int = Field(description="Messages exchanged (trainee + customer)")


class HistoryPage(BaseModel):
    items: list[HistoryItem]
    total: int = Field(description="Total sessions matching the filters")


class TranscriptMessage(BaseModel):
    role: MessageRole = Field(description="'user' = trainee, 'model' = AI customer")
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SessionDetail(HistoryItem):
    """A session with its full transcript and evaluation (if evaluated)."""

    messages: list[TranscriptMessage]
    evaluation: "EvaluationResultDetailResponse | None"


from src.domains.evaluations.schemas import EvaluationResultDetailResponse  # noqa: E402
from src.domains.scenarios.schemas import CategoryRef  # noqa: E402

HistoryScenario.model_rebuild()
SessionDetail.model_rebuild()
