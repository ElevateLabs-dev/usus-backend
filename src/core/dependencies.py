from dataclasses import dataclass
from enum import Enum
from typing import Sequence
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from src.core.config import settings

ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


class UserRole(str, Enum):
    PLATFORM_ADMIN = "platform_admin"
    COMPANY_ADMIN = "company_admin"
    MANAGER = "manager"
    TRAINEE = "trainee"


@dataclass
class AuthContext:
    user_id: UUID
    tenant_id: UUID | None  # None for unscoped platform-admin tokens
    role: UserRole


def get_auth_context(token: str = Depends(oauth2_scheme)) -> AuthContext:
    """
    FastAPI dependency that decodes a Bearer JWT and returns a full
    AuthContext (user_id, tenant_id, role).

    Raises HTTP 401 if the token is missing, malformed, expired, or
    does not contain the required claims.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        user_id_raw: str | None = payload.get("user_id")
        tenant_id_raw: str | None = payload.get("tenant_id")  # may be absent
        role_raw: str | None = payload.get("role")

        if not user_id_raw or not role_raw:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    try:
        return AuthContext(
            user_id=UUID(user_id_raw),
            tenant_id=UUID(tenant_id_raw) if tenant_id_raw else None,
            role=UserRole(role_raw),
        )
    except (ValueError, KeyError):
        raise credentials_exception


def get_current_tenant_id(
    ctx: AuthContext = Depends(get_auth_context),
) -> UUID:
    """
    Returns the tenant_id from the current AuthContext.  Raises 401 if the
    token carries no tenant (e.g. unscoped platform-admin token) — keeps all
    existing tenant-scoped routes working without any signature change.
    """
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant context required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return ctx.tenant_id


def require_roles(*allowed_roles: UserRole):
    """
    Dependency factory that enforces role-based access control.

    Returns a FastAPI dependency that resolves the AuthContext and raises
    HTTP 403 if the caller's role is not in ``allowed_roles``.

    Usage::

        @router.post("/admin-only", dependencies=[Depends(require_roles(UserRole.PLATFORM_ADMIN))])
        async def admin_only_route(): ...

    Or when you also need the context object::

        @router.get("/manager-view")
        async def view(ctx: AuthContext = Depends(require_roles(UserRole.MANAGER, UserRole.COMPANY_ADMIN))):
            ...
    """

    def _check(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if ctx.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Role '{ctx.role.value}' is not authorised for this action. "
                    f"Required: {[r.value for r in allowed_roles]}"
                ),
            )
        return ctx

    return _check
