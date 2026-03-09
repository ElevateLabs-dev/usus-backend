import enum
import uuid
from sqlalchemy import String, Text, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.base_model import TenantAwareBase
from src.domains.scenarios.models import Scenario


class SessionStatus(str, enum.Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    EVALUATED = "evaluated"


class MessageRole(str, enum.Enum):
    USER = "user"    # Trainee
    MODEL = "model"  # AI Customer
    SYSTEM = "system" # System instructions


class Session(TenantAwareBase):
    __tablename__ = "sessions"

    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenarios.id"), nullable=False, index=True
    )
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, name="session_status_enum"), default=SessionStatus.NOT_STARTED, nullable=False
    )

    scenario: Mapped[Scenario] = relationship()


class Message(TenantAwareBase):
    __tablename__ = "messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False, index=True
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, name="message_role_enum"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    session: Mapped[Session] = relationship()
