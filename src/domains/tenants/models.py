from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.base_model import Base

if TYPE_CHECKING:
    from src.domains.users.models import User


class Tenant(Base):
    """
    Root tenant entity — does NOT inherit TenantAwareBase because a Tenant
    IS the root of multi-tenancy, not a child of it.
    """

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Answers from the signup form
    company_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    referral_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Company logo in R2 storage
    logo_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Setup checklist: when the company launched, or hid the checklist
    launched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    checklist_dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # The evaluator also checks trainees against the knowledge base
    use_kb_for_evaluation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    users: Mapped[list["User"]] = relationship(
        "User",
        back_populates="tenant",
    )
