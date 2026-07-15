import os
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# Ensure ORM mappers are registered before sessions are used.
from src.domains.tenants import models as _tenants_models  # noqa: F401
from src.domains.users import models as _users_models  # noqa: F401

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/usus_db"
)

# initialize the async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=True,  # set to False in production
    pool_size=20,  # adjust based on concurrency needs
    max_overflow=10,
)

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
