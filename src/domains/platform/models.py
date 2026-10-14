from sqlalchemy import Boolean, false
from sqlalchemy.orm import Mapped, mapped_column

from src.core.base_model import Base


class PlatformSettings(Base):
    """
    Platform-wide switches set by platform admins. A single row, created the
    first time the settings are read.
    """

    __tablename__ = "platform_settings"

    # While true, only platform admins can sign in or use the API.
    maintenance_mode: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
