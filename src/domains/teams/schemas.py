from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class TeamCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    model_config = {
        "json_schema_extra": {
            "example": {"name": "Billing", "description": "Billing support desk"}
        }
    }


class TeamUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class TeamRead(BaseModel):
    id: UUID
    name: str
    description: str | None
    member_count: int
    scenario_count: int
    created_at: datetime


class TeamMemberRead(BaseModel):
    id: UUID
    email: str
    full_name: str | None
    role: str


class TeamScenarioRead(BaseModel):
    id: UUID
    name: str


class TeamDetail(TeamRead):
    members: list[TeamMemberRead]
    scenarios: list[TeamScenarioRead] = Field(
        description="Only this team's trainees (and other teams they are assigned "
        "to) see these"
    )


class MemberIds(BaseModel):
    user_ids: list[UUID] = Field(min_length=1, max_length=500)


class ScenarioIds(BaseModel):
    scenario_ids: list[UUID] = Field(
        max_length=500,
        description="The team's scenarios; replaces the current list",
    )
