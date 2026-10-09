# from pydantic_settings import BaseSettings, SettingsConfigDict
# from typing import Optional


# class Settings(BaseSettings):
#     # core
#     PROJECT_NAME: str = "Usus Backend"
#     ENVIRONMENT: str = "local"
#     SECRET_KEY: str

#     # infrastructure
#     DATABASE_URL: str
#     CELERY_BROKER_URL: str
#     CELERY_RESULT_BACKEND: str

#     # Admin dashboard credentials
#     ADMIN_USERNAME: str = "admin"
#     ADMIN_PASSWORD: str

#     # AI Providers (Optional locally so the app doesn't crash if you leave them blank at first)
#     OPENAI_API_KEY: Optional[str] = None
#     ANTHROPIC_API_KEY: Optional[str] = None

#     # AWS Storage (Optional locally)
#     AWS_ACCESS_KEY_ID: Optional[str] = None
#     AWS_SECRET_ACCESS_KEY: Optional[str] = None
#     AWS_REGION: Optional[str] = None
#     AWS_S3_BUCKET_NAME: Optional[str] = None

#     # This tells Pydantic to read from the .env file in the root directory
#     model_config = SettingsConfigDict(env_file=".env", extra="ignore")


# # Create a single instance of the settings to be imported and used across the app
# settings = Settings()


# ====================================

from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # core
    PROJECT_NAME: str = "Usus Backend"
    ENVIRONMENT: str = "local"
    SECRET_KEY: str

    # infrastructure
    # Any Postgres URL, e.g. Neon's "postgresql://...?sslmode=require"
    # (adapted for asyncpg by async_database_url below).
    DATABASE_URL: str

    # Admin dashboard credentials
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str

    # AI Providers
    # Which LLM backs the simulation + evaluation engines: "openai" or "anthropic"
    LLM_PROVIDER: str = "openai"
    # Seconds before an LLM call is abandoned, so a slow model can't hang a request
    LLM_TIMEOUT_SECONDS: float = 60.0

    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4.1-mini"
    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_MODEL: str = "claude-haiku-4-5"

    # Email (trainee invites) via Resend. Without an API key, emails are only
    # printed to the server log (local development).
    RESEND_API_KEY: Optional[str] = None
    # Must be on a domain verified in Resend (onboarding@resend.dev works for testing)
    EMAIL_FROM: str = "Usus <onboarding@resend.dev>"
    # Where trainees sign in; used for the link in invite emails
    FRONTEND_URL: str = "http://localhost:3000"

    # AWS Storage
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: Optional[str] = None
    AWS_S3_BUCKET_NAME: Optional[str] = None

    # This tells Pydantic to read from the .env file in the root directory
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()


def async_database_url(url: str) -> str:
    """
    Adapt a standard Postgres URL (e.g. copied from Neon) for SQLAlchemy + asyncpg:
    - postgres:// or postgresql://  ->  postgresql+asyncpg://
    - sslmode=require               ->  ssl=require (asyncpg's name for it)
    - channel_binding=...           ->  dropped (not an asyncpg option)
    """
    parts = urlsplit(url)
    scheme = parts.scheme
    if scheme in ("postgres", "postgresql"):
        scheme = "postgresql+asyncpg"

    query = dict(parse_qsl(parts.query))
    sslmode = query.pop("sslmode", None)
    query.pop("channel_binding", None)
    if sslmode and "ssl" not in query:
        query["ssl"] = sslmode

    return urlunsplit(
        (scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )
