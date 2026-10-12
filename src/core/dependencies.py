from dataclasses import dataclass
from enum import Enum
from typing import Sequence
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_db

ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


class UserRole(str, Enum):
    PLATFORM_ADMIN = "platform_admin"
    COMPANY_ADMIN = "company_admin"
    MANAGER = "manager"
    TRAINEE = "trainee"


# Imported here (not at the top): these modules import UserRole from this file.
from src.domains.tenants.models import Tenant  # noqa: E402
from src.domains.users.models import User  # noqa: E402


@dataclass
class AuthContext:
    user_id: UUID
    tenant_id: UUID | None  # None for unscoped platform-admin tokens
    role: UserRole
    must_change_password: bool = False


async def get_auth_context_allow_password_change(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    """
    Decodes a Bearer JWT and loads the user, WITHOUT enforcing the first-login
    password change. Only for the endpoints a user needs while their temporary
    password is still active (change-password, /users/me).

    The token only proves who the caller is. Their role, organization and
    status are read from the database on every request, so deactivating a user
    or organization — or changing a role — takes effect immediately.

    Raises HTTP 401 if the token is missing, malformed or expired, or the user
    no longer exists or is deactivated; HTTP 403 if their organization is
    deactivated.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        user_id = UUID(payload.get("user_id") or "")
        tenant_claim: str | None = payload.get("tenant_id")  # may be absent
    except (JWTError, ValueError):
        raise credentials_exception

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise credentials_exception

    try:
        role = UserRole(user.role)
        # Platform admins belong to no organization; their token may name the
        # one they are acting in. Everyone else uses their own organization.
        tenant_id = user.tenant_id
        if tenant_id is None and role == UserRole.PLATFORM_ADMIN and tenant_claim:
            tenant_id = UUID(tenant_claim)
    except ValueError:
        raise credentials_exception

    if tenant_id is not None and role != UserRole.PLATFORM_ADMIN:
        tenant = await db.get(Tenant, tenant_id)
        if tenant is not None and not tenant.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your organization has been deactivated",
            )

    return AuthContext(
        user_id=user.id,
        tenant_id=tenant_id,
        role=role,
        must_change_password=user.must_change_password,
    )


def get_auth_context(
    ctx: AuthContext = Depends(get_auth_context_allow_password_change),
) -> AuthContext:
    """
    FastAPI dependency that returns the caller's AuthContext (user_id,
    tenant_id, role).

    Raises HTTP 401 for invalid tokens, and HTTP 403 while the user still has
    to replace their temporary password.
    """
    if ctx.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password change required",
        )
    return ctx


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
