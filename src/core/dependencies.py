from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from src.core.config import settings

ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


def get_current_tenant_id(token: str = Depends(oauth2_scheme)) -> UUID:
    """
    FastAPI dependency that extracts and validates the tenant_id from a
    Bearer JWT token.

    Raises HTTP 401 if the token is missing, malformed, expired, or does
    not contain a 'tenant_id' claim.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        tenant_id_raw: str | None = payload.get("tenant_id")
        if tenant_id_raw is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    try:
        return UUID(tenant_id_raw)
    except ValueError:
        raise credentials_exception
