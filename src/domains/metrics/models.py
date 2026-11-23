from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.core.base_model import TenantAwareBase


class Metric(TenantAwareBase):
    """
    A company's own evaluation metric, on top of the 7 default ones
    (src/core/training.py). Scenarios pick the metrics they are scored on.
    """

    __tablename__ = "metrics"
    __table_args__ = (UniqueConstraint("tenant_id", "key"),)

    # Stable id used in scenarios and scores, made from the first name
    key: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # What the evaluator scores, e.g. "Offers the loyalty discount when..."
    description: Mapped[str] = mapped_column(Text, nullable=False)
