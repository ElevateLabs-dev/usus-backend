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
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_db
from src.core.dependencies import (
    ALGORITHM,
    AuthContext,
    get_auth_context_allow_password_change,
)
from src.core.security import MIN_PASSWORD_LENGTH, hash_password, verify_password
from src.domains.users import crud as users_crud
from src.domains.users.models import User

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])

_ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = _ACCESS_TOKEN_EXPIRE_MINUTES * 60  # seconds
    # True until an invited user replaces their temporary password; every other
    # endpoint returns 403 "Password change required" until then.
    must_change_password: bool = False


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(description="The temporary or current password")
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH)

    model_config = {
        "json_schema_extra": {
            "example": {
                "current_password": "temporary-password-from-email",
                "new_password": "my-new-secure-password",
            }
        }
    }


def _issue_token(user: User, tenant_id: UUID | None) -> TokenResponse:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload: dict = {
        "user_id": str(user.id),
        "email": user.email,  # PCMadumere. Added this so to be able to get the email from the token
        "role": user.role,
        "exp": expire,
    }
    if tenant_id is not None:
        payload["tenant_id"] = str(tenant_id)
    if user.must_change_password:
        payload["pwd_change"] = True

    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)
    return TokenResponse(
        access_token=token, must_change_password=user.must_change_password
    )


@router.post(
    "/token",
    summary="Sign in",
    description=(
        "OAuth2 password form: send `username` (the email, case-insensitive) and "
        "`password` as form fields. Returns a Bearer token valid for 24 hours.\n\n"
        "If `must_change_password` is **true** (first sign-in with a temporary "
        "password), every endpoint except `GET /users/me` and "
        "`POST /auth/change-password` returns **403 Password change required** "
        "until the password is changed.\n\n"
        "Platform admins (no organization) may pass `?tenant_id=` to act inside "
        "one organization."
    ),
    responses={401: {"description": "Incorrect email or password"}},
)
async def issue_token(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[
        UUID | None,
        Query(description="Scope token to tenant (platform admins only)"),
    ] = None,
) -> TokenResponse:
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect email or password",
        headers={"WWW-Authenticate": "Bearer"},
    )

    user = await users_crud.user.get_by_email(db, form.username)
    if user is None or not user.is_active:
        raise invalid
    if not verify_password(form.password, user.hashed_password):
        raise invalid

    # Platform admins can optionally receive a tenant-scoped token.
    effective_tenant_id = user.tenant_id
    if user.tenant_id is None and tenant_id is not None:
        effective_tenant_id = tenant_id

    return _issue_token(user, effective_tenant_id)


@router.post(
    "/change-password",
    summary="Change your password",
    description=(
        "Replace your password (minimum 8 characters). Required after the first "
        "sign-in with a temporary password; also usable any time later.\n\n"
        "Returns a **new token** — use it instead of the old one, which still "
        "carries the password-change restriction."
    ),
    responses={
        400: {"description": "Current password is wrong, or the new one is the same"},
        401: {"description": "Missing or invalid token"},
    },
)
async def change_password(
    body: ChangePasswordRequest,
    ctx: Annotated[AuthContext, Depends(get_auth_context_allow_password_change)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """
    Works with the temporary-password token from first sign-in. Returns a
    fresh token without the password-change restriction.
    """
    user = await users_crud.user.get(db, id=ctx.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    if body.new_password == body.current_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from the current password",
        )

    user.hashed_password = hash_password(body.new_password)
    user.must_change_password = False
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Keep the tenant scope of the token the user is currently using.
    return _issue_token(user, ctx.tenant_id)
