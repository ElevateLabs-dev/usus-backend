import enum
from sqlalchemy import String, Text, Enum
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
    persona: Mapped[CustomerPersona] = mapped_column(
        Enum(CustomerPersona, name="customer_persona_enum"), nullable=False
    )
    difficulty: Mapped[DifficultyLevel] = mapped_column(
        Enum(DifficultyLevel, name="difficulty_level_enum"), nullable=False
    )
