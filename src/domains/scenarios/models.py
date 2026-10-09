import enum
from typing import Optional

from sqlalchemy import JSON, Enum, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.base_model import TenantAwareBase


class CustomerPersona(str, enum.Enum):
    FRIENDLY = "friendly"
    FRUSTRATED = "frustrated"
    ANGRY = "angry"


class DifficultyLevel(str, enum.Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class Scenario(TenantAwareBase):
    __tablename__ = "scenarios"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    persona: Mapped[CustomerPersona] = mapped_column(
        Enum(CustomerPersona, name="customer_persona_enum"), nullable=False
    )
    difficulty: Mapped[DifficultyLevel] = mapped_column(
        Enum(DifficultyLevel, name="difficulty_level_enum"), nullable=False
    )

    # --- Organization (see src/core/training.py) ---
    # TrainingCategory value; nullable only for scenarios created before categories.
    category: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, index=True
    )
    # List of SkillDimension values this scenario tests, e.g. ["empathy", "resolution"]
    skills: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'")
    )
    estimated_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10, server_default=text("10")
    )

    # --- Pre-roleplay brief (shown to the trainee) ---
    customer_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    customer_personality: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    customer_emotion: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    customer_background: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    situation: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # what happened
    customer_goal: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    trainee_objective: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Policies / facts the trainee may use: [{"label": "...", "content": "..."}]
    important_information: Mapped[list[dict]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'")
    )

    # --- Hidden from trainees: steer the AI customer and the evaluator ---
    escalation_behavior: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    success_criteria: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
