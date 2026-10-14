from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from src.domains.users.schemas import OrgUserRead


class TenantCreate(BaseModel):
    name: str
    is_active: bool = True


class TenantUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None


class TenantRead(BaseModel):
    id: UUID
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Organization onboarding API (platform admins)
# ---------------------------------------------------------------------------


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255, description="Organization name")
    admin_email: EmailStr = Field(
        description="The organization's first company admin; they are emailed an "
        "invite with a temporary password"
    )
    admin_full_name: str | None = Field(
        default=None, max_length=255, description="Primary contact's name"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Acme Retail",
                "admin_email": "head.of.cs@acme.com",
                "admin_full_name": "Ada Obi",
            }
        }
    }


class CompanyAdminCreate(BaseModel):
    email: EmailStr = Field(description="Stored lower-case")
    full_name: str | None = Field(default=None, max_length=255)

    model_config = {
        "json_schema_extra": {
            "example": {"email": "ops.lead@acme.com", "full_name": "Bola Ade"}
        }
    }


class StaffUpdate(BaseModel):
    is_active: bool = Field(
        description="false removes the user's access immediately; true restores it"
    )


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    is_active: bool | None = Field(
        default=None,
        description="false deactivates the organization: its users can no longer "
        "sign in or use the API. Nothing is deleted.",
    )


class OrganizationRead(BaseModel):
    id: UUID
    name: str
    is_active: bool
    created_at: datetime
    users_count: int = Field(description="All users in the organization")
    trainees_count: int
    scenarios_count: int = Field(description="Active (not archived) scenarios")
    sessions_completed: int = Field(description="Evaluated training sessions")


class OrganizationDetail(OrganizationRead):
    staff: list[OrgUserRead] = Field(
        description="The organization's company admins and managers"
    )
