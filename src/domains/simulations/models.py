import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, exists, or_
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.base_model import TenantAwareBase
from src.domains.scenarios.models import Scenario
from src.domains.users.models import User


class SessionStatus(str, enum.Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    EVALUATED = "evaluated"


class MessageRole(str, enum.Enum):
    USER = "user"       # Trainee
    MODEL = "model"     # AI Customer
    SYSTEM = "system"   # System instructions


class Session(TenantAwareBase):
    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scenarios.id"),
        nullable=False,
        index=True,
    )

    status: Mapped[SessionStatus] = mapped_column(
        Enum(
            SessionStatus,
            name="session_status_enum",
        ),
        default=SessionStatus.NOT_STARTED,
        nullable=False,
    )

    # Set when the trainee ends the session (start time is created_at)
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Voice sessions: the Vapi assistant created for this session and the
    # call it was used in (both None for text sessions).
    voice_assistant_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    voice_call_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    scenario: Mapped[Scenario] = relationship()

    user: Mapped[User | None] = relationship()


class Message(TenantAwareBase):
    __tablename__ = "messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id"),
        nullable=False,
        index=True,
    )

    role: Mapped[MessageRole] = mapped_column(
        Enum(
            MessageRole,
            name="message_role_enum",
        ),
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    session: Mapped[Session] = relationship()


def has_activity():
    """
    SQL condition: the session is not an empty, unfinished one.

    Opening the role-play page used to start a session straight away, so
    trainees have sessions they never used. Those are left out of history
    and progress.
    """
    trainee_spoke = exists().where(
        Message.session_id == Session.id, Message.role == MessageRole.USER
    )
    return or_(Session.status != SessionStatus.IN_PROGRESS, trainee_spoke)
