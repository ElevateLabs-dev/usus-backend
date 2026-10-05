from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.domains.simulations.models import SessionStatus, MessageRole


class SessionBase(BaseModel):
    scenario_id: UUID
    status: SessionStatus = SessionStatus.NOT_STARTED


class SessionCreate(SessionBase):
    user_id: UUID | None = None


class SessionUpdate(BaseModel):
    status: SessionStatus | None = None


class SessionResponse(SessionBase):
    id: UUID
    tenant_id: UUID
    user_id: UUID | None = None

    model_config = ConfigDict(from_attributes=True)


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


# --- Request schemas ---


class StartSessionRequest(BaseModel):
    scenario_id: UUID


class SendMessageRequest(BaseModel):
    content: str


# --- Composite response schemas ---


class SendMessageResponse(BaseModel):
    user_message: MessageResponse
    ai_reply: MessageResponse


class EndSessionResponse(BaseModel):
    session: SessionResponse
    evaluation: "EvaluationResultDetailResponse"


from src.domains.evaluations.schemas import EvaluationResultDetailResponse  # noqa: E402

EndSessionResponse.model_rebuild()