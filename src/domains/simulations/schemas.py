from uuid import UUID
from pydantic import BaseModel, ConfigDict
from src.domains.simulations.models import SessionStatus, MessageRole


class SessionBase(BaseModel):
    scenario_id: UUID
    status: SessionStatus = SessionStatus.NOT_STARTED


class SessionCreate(SessionBase):
    pass


class SessionUpdate(BaseModel):
    status: SessionStatus | None = None


class SessionResponse(SessionBase):
    id: UUID
    tenant_id: UUID

    model_config = ConfigDict(from_attributes=True)


class MessageBase(BaseModel):
    session_id: UUID
    role: MessageRole
    content: str


class MessageCreate(MessageBase):
    pass


class MessageUpdate(MessageBase):
    pass  # Messages typically aren't updated, but required by CRUDBase


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


# Resolved at import time — avoids circular import by using TYPE_CHECKING guard approach.
# The string annotation is resolved via model_rebuild() called in the router module.
from src.domains.evaluations.schemas import EvaluationResultDetailResponse  # noqa: E402

EndSessionResponse.model_rebuild()
