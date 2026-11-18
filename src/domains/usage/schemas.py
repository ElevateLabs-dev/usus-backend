from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class UsageTotals(BaseModel):
    sessions: int
    text_sessions: int
    voice_sessions: int
    session_minutes: float = Field(description="Time from start to end of the sessions")
    voice_minutes: float = Field(description="Length of the voice calls")
    input_tokens: int
    output_tokens: int
    ai_cost: float = Field(description="OpenAI (or Anthropic) cost in USD")
    voice_cost: float = Field(description="Vapi cost in USD")
    total_cost: float


class OrganizationUsage(BaseModel):
    organization_id: UUID
    organization_name: str
    sessions: int
    voice_minutes: float
    ai_cost: float
    voice_cost: float
    total_cost: float


class SessionUsage(BaseModel):
    session_id: UUID
    organization_id: UUID
    organization_name: str
    trainee_name: str | None
    trainee_email: str | None
    scenario_name: str | None
    mode: str = Field(description="'text' or 'voice'")
    status: str
    started_at: datetime
    ended_at: datetime | None
    duration_seconds: int | None = Field(description="None while still in progress")
    voice_seconds: int
    input_tokens: int
    output_tokens: int
    conversation_cost: float = Field(description="AI cost of the customer's replies")
    evaluation_cost: float = Field(description="AI cost of scoring the session")
    voice_cost: float
    total_cost: float


class UsageReport(BaseModel):
    days: int
    since: datetime
    totals: UsageTotals
    organizations: list[OrganizationUsage] = Field(
        description="Per organization, most expensive first (platform admins only)"
    )
    sessions: list[SessionUsage] = Field(description="Latest sessions, newest first")
