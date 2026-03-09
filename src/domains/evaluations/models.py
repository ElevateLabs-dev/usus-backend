import uuid
from sqlalchemy import String, Text, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.base_model import Base, TenantAwareBase
from src.domains.simulations.models import Session


class EvaluationResult(TenantAwareBase):
    __tablename__ = "evaluation_results"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False, unique=True, index=True
    )
    overall_score: Mapped[int] = mapped_column(Integer, nullable=True) # Could be 0-100
    summary: Mapped[str] = mapped_column(Text, nullable=True)

    session: Mapped[Session] = relationship()
    dimension_scores: Mapped[list["DimensionScore"]] = relationship(back_populates="evaluation")
    red_flags: Mapped[list["RedFlag"]] = relationship(back_populates="evaluation")


class DimensionScore(Base):
    __tablename__ = "dimension_scores"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluation_results.id"), nullable=False, index=True
    )
    dimension_name: Mapped[str] = mapped_column(String(255), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)

    evaluation: Mapped[EvaluationResult] = relationship(back_populates="dimension_scores")


class RedFlag(Base):
    __tablename__ = "red_flags"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluation_results.id"), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    evaluation: Mapped[EvaluationResult] = relationship(back_populates="red_flags")
