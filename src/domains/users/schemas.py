from uuid import UUID

from pydantic import BaseModel, EmailStr

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
 