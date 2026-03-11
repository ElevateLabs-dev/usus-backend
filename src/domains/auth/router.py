"""
Auth router — OAuth2 password grant endpoint.

Looks up the user by email, verifies the bcrypt password, and returns
a signed JWT. Platform admins (tenant_id=None) may pass an optional
`?tenant_id=` query parameter to produce a scoped token.
"""

from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_db
from src.core.dependencies import ALGORITHM, UserRole
from src.core.security import verify_password
from src.domains.users import crud as users_crud

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])

_ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = _ACCESS_TOKEN_EXPIRE_MINUTES * 60  # seconds


@router.post("/token", summary="Obtain a Bearer JWT")
async def issue_token(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    tenant_id: Annotated[
        UUID | None,
        Query(default=None, description="Scope token to tenant (platform admins only)"),
    ] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = Depends(get_db),
) -> TokenResponse:
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect email or password",
        headers={"WWW-Authenticate": "Bearer"},
    )

    user = await users_crud.get_by_email(db, form.username)
    if user is None or not user.is_active:
        raise invalid
    if not verify_password(form.password, user.hashed_password):
        raise invalid

    # Platform admins can optionally receive a tenant-scoped token.
    effective_tenant_id = user.tenant_id
    if user.tenant_id is None and tenant_id is not None:
        effective_tenant_id = tenant_id

    expire = datetime.now(timezone.utc) + timedelta(
        minutes=_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload: dict = {
        "user_id": str(user.id),
        "role": user.role,
        "exp": expire,
    }
    if effective_tenant_id is not None:
        payload["tenant_id"] = str(effective_tenant_id)

    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)
    return TokenResponse(access_token=token)
