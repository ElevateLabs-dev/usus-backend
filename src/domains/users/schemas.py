from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from src.core.dependencies import UserRole


class UserCreate(BaseModel):
    email: EmailStr
    role: UserRole
    tenant_id: UUID | None = None
    is_active: bool = True


class UserRead(BaseModel):
    id: UUID
    email: EmailStr
    role: UserRole
    tenant_id: UUID | None
    is_active: bool

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    role: UserRole | None = None
    tenant_id: UUID | None = None
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# Trainee onboarding (organization adds its own trainees)
# ---------------------------------------------------------------------------

MAX_BULK_TRAINEES = 500


class ErrorResponse(BaseModel):
    detail: str


class TraineeCreate(BaseModel):
    email: EmailStr = Field(description="Trainee's email; stored lower-case")
    full_name: str | None = Field(
        default=None, max_length=255, description="Used in the invite email"
    )

    model_config = {
        "json_schema_extra": {
            "example": {"email": "jane.doe@acme.com", "full_name": "Jane Doe"}
        }
    }


class BulkTraineeCreate(BaseModel):
    trainees: list[TraineeCreate] = Field(
        min_length=1,
        max_length=MAX_BULK_TRAINEES,
        description=f"Between 1 and {MAX_BULK_TRAINEES} trainees",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "trainees": [
                    {"email": "jane.doe@acme.com", "full_name": "Jane Doe"},
                    {"email": "john.smith@acme.com", "full_name": "John Smith"},
                ]
            }
        }
    }


class OrgUserRead(BaseModel):
    """A user as seen by their organization's admins/managers and by themselves."""

    id: UUID
    email: EmailStr
    full_name: str | None
    role: UserRole
    tenant_id: UUID | None = Field(description="The user's organization")
    is_active: bool
    must_change_password: bool = Field(
        description="True until the user replaces their temporary password"
    )
    invite_sent_at: datetime | None = Field(
        description="When the last invite email was sent; null if it failed or "
        "has not gone out yet"
    )
    created_at: datetime

    model_config = {"from_attributes": True}


class SkippedTrainee(BaseModel):
    email: str
    reason: str = Field(
        description="'Invalid email address', 'Duplicate in this upload' or "
        "'Email already registered'"
    )


class BulkTraineeResult(BaseModel):
    created: list[OrgUserRead] = Field(description="Trainees created and invited")
    skipped: list[SkippedTrainee] = Field(description="Rows that were not created")


class InviteResendResponse(BaseModel):
    status: str = Field(
        description="Always 'sending'; the email goes out in the background"
    )
    email: EmailStr
