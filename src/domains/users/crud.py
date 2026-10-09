from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.base_crud import CRUDBaseRoot
from src.domains.users.models import User
from src.domains.users.schemas import UserCreate, UserUpdate


class CRUDUser(CRUDBaseRoot[User, UserCreate, UserUpdate]):
    async def get_by_email(self, db: AsyncSession, email: str) -> User | None:
        # Case-insensitive so "Jane@Org.com" and "jane@org.com" are the same account.
        result = await db.execute(
            select(self.model).where(func.lower(self.model.email) == email.lower())
        )
        return result.scalar_one_or_none()

    async def create(  # type: ignore[override]
        self, db: AsyncSession, *, obj_in: UserCreate, hashed_password: str
    ) -> User:
        db_obj = User(
            email=obj_in.email,
            hashed_password=hashed_password,
            role=obj_in.role.value,
            tenant_id=obj_in.tenant_id,
            is_active=obj_in.is_active,
        )
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def update(  # type: ignore[override]
        self, db: AsyncSession, *, id: UUID, obj_in: UserUpdate
    ) -> User | None:
        db_obj = await self.get(db=db, id=id)
        if not db_obj:
            return None

        update_data = obj_in.model_dump(exclude_unset=True)
        update_data.pop("id", None)
        for field, value in update_data.items():
            if field == "role" and value is not None:
                value = value.value  # store the string value of the enum
            setattr(db_obj, field, value)

        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj


user = CRUDUser(User)
