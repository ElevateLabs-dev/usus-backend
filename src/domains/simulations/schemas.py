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
    pass # Messages typically aren't updated, but required by CRUDBase


class MessageResponse(MessageBase):
    id: UUID
    tenant_id: UUID

    model_config = ConfigDict(from_attributes=True)
