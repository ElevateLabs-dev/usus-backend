import uuid
from sqlalchemy import Boolean, Column, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.base_model import Base


class Tenant(Base):
    """
    Root tenant entity — does NOT inherit TenantAwareBase because a Tenant
    IS the root of multi-tenancy, not a child of it.
    """

    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        onupdate=func.now(),
        server_default=func.now(),
        nullable=False,
    )
