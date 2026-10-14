from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class CheckState(str, Enum):
    OK = "ok"
    NOT_CONFIGURED = "not_configured"
    ERROR = "error"


class StatusCheck(BaseModel):
    name: str = Field(description="'api', 'database', 'email' or 'ai'")
    state: CheckState
    detail: str = Field(description="Short human-readable explanation")


class PlatformStatus(BaseModel):
    overall: str = Field(
        description="'operational' when every check is ok, 'maintenance' while "
        "maintenance mode is on, otherwise 'degraded'"
    )
    environment: str
    version: str
    maintenance_mode: bool
    checks: list[StatusCheck]
    checked_at: datetime


class ActivityType(str, Enum):
    ORGANIZATION_CREATED = "organization_created"
    USER_ADDED = "user_added"
    SESSION_COMPLETED = "session_completed"


class ActivityItem(BaseModel):
    type: ActivityType
    message: str
    organization_id: UUID | None
    organization_name: str | None
    occurred_at: datetime


class AlertType(str, Enum):
    INVITE_NOT_DELIVERED = "invite_not_delivered"
    EVALUATION_MISSING = "evaluation_missing"


class AlertItem(BaseModel):
    type: AlertType
    message: str
    organization_id: UUID | None
    organization_name: str | None
    occurred_at: datetime = Field(description="When the problem started")


class PlatformSettingsRead(BaseModel):
    maintenance_mode: bool = Field(
        description="While true, only platform admins can sign in or use the API; "
        "everyone else gets 503"
    )
    updated_at: datetime | None


class PlatformSettingsUpdate(BaseModel):
    maintenance_mode: bool

    model_config = {"json_schema_extra": {"example": {"maintenance_mode": True}}}


class PlatformAdminCreate(BaseModel):
    email: EmailStr = Field(description="Stored lower-case")
    full_name: str | None = Field(default=None, max_length=255)

    model_config = {
        "json_schema_extra": {
            "example": {"email": "ops@meetusus.com", "full_name": "Chidi Okafor"}
        }
    }


class PlatformAdminUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)
    is_active: bool | None = Field(
        default=None,
        description="false removes their access immediately. You cannot "
        "deactivate yourself.",
    )
