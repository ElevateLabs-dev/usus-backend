from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.users.models import User
from src.domains.users.schemas import UserCreate, UserUpdate


async def get_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_by_id(db: AsyncSession, user_id: UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def create(db: AsyncSession, data: UserCreate, hashed_password: str) -> User:
    user = User(
        email=data.email,
        hashed_password=hashed_password,
        role=data.role.value,
        tenant_id=data.tenant_id,
        is_active=data.is_active,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def update(db: AsyncSession, user: User, data: UserUpdate) -> User:
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "role" and value is not None:
            value = value.value  # store the string value of the enum
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return user
