import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, false
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.base_model import Base

if TYPE_CHECKING:
    from src.domains.tenants.models import Tenant


class User(Base):
    """
    Application user. Not tenant-aware at the model level because platform
    admins have no tenant; tenant_id is nullable and merely indexed.
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(254), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Org-added users must replace their temporary password on first sign-in.
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    # When the invite email (with the temporary password) was last sent successfully.
    invite_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    tenant: Mapped["Tenant | None"] = relationship(
        "Tenant",
        back_populates="users",
    )
