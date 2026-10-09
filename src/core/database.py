import uuid
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.core.config import async_database_url, settings

# Ensure ORM mappers are registered before sessions are used.
from src.domains.tenants import models as _tenants_models  # noqa: F401
from src.domains.users import models as _users_models  # noqa: F401

DATABASE_URL = async_database_url(settings.DATABASE_URL)


def _engine_options(url: str) -> dict[str, Any]:
    options: dict[str, Any] = {
        # Log SQL (with values) only in local development.
        "echo": settings.ENVIRONMENT == "local",
        # Neon suspends idle databases, which drops open connections: check a
        # connection before using it and recycle old ones.
        "pool_pre_ping": True,
    }

    if settings.DB_NULL_POOL:
        options["poolclass"] = NullPool
    else:
        options.update(pool_size=5, max_overflow=5, pool_recycle=300)

    if "-pooler." in url:
        # Neon's pooled endpoint (PgBouncer, transaction mode) cannot reuse
        # asyncpg's prepared statements across connections.
        options["connect_args"] = {
            "statement_cache_size": 0,
            "prepared_statement_name_func": lambda: f"__asyncpg_{uuid.uuid4()}__",
        }
    return options


# initialize the async engine
engine = create_async_engine(DATABASE_URL, **_engine_options(DATABASE_URL))

# create a session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # prevent attributes from being expired after commit
    autoflush=False,  # disable autoflush for better performance in some cases
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that provides an async database session."""
    async with AsyncSessionLocal() as session:
        yield session
