import uuid
from sqlalchemy import JSON, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.base_model import Base, TenantAwareBase
from src.domains.simulations.models import Session


class EvaluationResult(TenantAwareBase):
    __tablename__ = "evaluation_results"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    overall_score: Mapped[int] = mapped_column(Integer, nullable=True)  # 0-100
    summary: Mapped[str] = mapped_column(Text, nullable=True)
    # Feedback lists (strings): what went well, what went poorly, what the trainee
    # could have done, and concrete suggestions for next time.
    strengths: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'")
    )
    improvements: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'")
    )
    missed_opportunities: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'")
    )
    recommendations: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'")
    )

    session: Mapped[Session] = relationship()
    dimension_scores: Mapped[list["DimensionScore"]] = relationship(
        back_populates="evaluation"
    )
    red_flags: Mapped[list["RedFlag"]] = relationship(back_populates="evaluation")


class DimensionScore(Base):
    __tablename__ = "dimension_scores"

    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_results.id"),
        nullable=False,
        index=True,
    )
    # SkillDimension value (e.g. "de_escalation"); null for pre-0-100 evaluations
    dimension_key: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True
    )
    dimension_name: Mapped[str] = mapped_column(String(255), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-100
    rationale: Mapped[str] = mapped_column(Text, nullable=False)

    evaluation: Mapped[EvaluationResult] = relationship(
        back_populates="dimension_scores"
    )


class RedFlag(Base):
    __tablename__ = "red_flags"

    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_results.id"),
        nullable=False,
        index=True,
    )
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    evaluation: Mapped[EvaluationResult] = relationship(back_populates="red_flags")
