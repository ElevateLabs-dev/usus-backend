from uuid import UUID

from pydantic import BaseModel, ConfigDict

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


class SessionResponse(SessionBase):
    id: UUID
    tenant_id: UUID
    user_id: UUID | None = None

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