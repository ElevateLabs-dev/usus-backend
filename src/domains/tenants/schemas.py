from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


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
