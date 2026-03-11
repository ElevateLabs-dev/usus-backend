"""
Auth router — stub token endpoint for development.

This issues a signed JWT for the supplied claims without validating
credentials against a database.  In production this would be replaced
with a proper credential-validation flow (e.g. OAuth2 password grant
against a User table, or an external IdP token exchange).
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter
from jose import jwt
from pydantic import BaseModel

from src.core.config import settings
from src.core.dependencies import ALGORITHM, UserRole

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])

# Token lifetime — long for dev convenience; tighten in production.
_ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours


class TokenRequest(BaseModel):
    user_id: UUID
    tenant_id: UUID
    role: UserRole


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = _ACCESS_TOKEN_EXPIRE_MINUTES * 60  # seconds


@router.post(
    "/token",
    summary="Issue a development JWT (stub)",
    description=(
        "**Development stub.** Returns a signed JWT for the provided "
        "`user_id`, `tenant_id`, and `role` without any credential check. "
        "Replace with a real auth flow before going to production."
    ),
)
async def issue_token(body: TokenRequest) -> TokenResponse:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "user_id": str(body.user_id),
        "tenant_id": str(body.tenant_id),
        "role": body.role.value,
        "exp": expire,
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)
    return TokenResponse(access_token=token)
