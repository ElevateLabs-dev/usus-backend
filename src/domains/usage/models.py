import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.base_model import TenantAwareBase


class UsageRecord(TenantAwareBase):
    """
    One paid call made for a training session: an AI (LLM) request, or a
    finished Vapi voice call.
    """

    __tablename__ = "usage_records"

    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=True, index=True
    )
    # "llm" or "voice"
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # What the call was for: "conversation", "voice_conversation", "evaluation"
    # or "voice_call".
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # In US dollars; None when the price of the model is not known.
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
