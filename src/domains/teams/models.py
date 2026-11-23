import uuid

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.base_model import TenantAwareBase


class Team(TenantAwareBase):
    """A group of users in an organization, e.g. a department."""

    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class TeamMember(TenantAwareBase):
    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("team_id", "user_id"),)

    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class TeamScenario(TenantAwareBase):
    """
    A scenario assigned to a team. A scenario with no team is for everyone;
    one with teams is only shown to those teams' trainees.
    """

    __tablename__ = "team_scenarios"
    __table_args__ = (UniqueConstraint("team_id", "scenario_id"),)

    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scenarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
