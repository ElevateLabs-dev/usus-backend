from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
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
    users: Mapped[list["User"]] = relationship(
        "User",
        back_populates="tenant",
    )
