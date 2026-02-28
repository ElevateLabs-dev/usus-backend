from typing import Any, Generic, Sequence, TypeVar
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.base_model import TenantAwareBase


# Define generic types for the Model and Pydantic schemas
ModelType = TypeVar("ModelType", bound=TenantAwareBase)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)


class CRUDBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """
    CRUD object with default methods to Create, Read, Update, Delete (CRUD).
    Enforces multi-tenancy by requiring `tenant_id` (UUID) in all operations.
    """

    def __init__(self, model: type[ModelType]):
        self.model = model

    async def get(
        self, db: AsyncSession, id: UUID, tenant_id: UUID
    ) -> ModelType | None:
        """Fetch a single record, strictly filtered by tenant_id."""
        query = select(self.model).where(
            self.model.id == id, self.model.tenant_id == tenant_id
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_multi(
        self, db: AsyncSession, tenant_id: UUID, skip: int = 0, limit: int = 100
    ) -> Sequence[ModelType]:
        """Fetch multiple records, strictly filtered by tenant_id."""
        query = (
            select(self.model)
            .where(self.model.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(query)
        return result.scalars().all()

    async def create(
        self, db: AsyncSession, *, obj_in: CreateSchemaType, tenant_id: UUID
    ) -> ModelType:
        """Create a new record, forcefully injecting the tenant_id."""
        obj_in_data = obj_in.model_dump()
        # create the model instance and inject the tenant_id
        db_obj = self.model(**obj_in_data, tenant_id=tenant_id)

        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def update(
        self, db: AsyncSession, *, id: UUID, obj_in: UpdateSchemaType, tenant_id: UUID
    ) -> ModelType | None:
        """Update a record, ensuring the tenant owns it before updating."""
        # First, ensure the object exists and belongs to the tenant
        db_obj = await self.get(db=db, id=id, tenant_id=tenant_id)
        if not db_obj:
            return None  # TODO: consider raising an exception here instead for better error handling

        update_data = (
            obj_in
            if isinstance(obj_in, dict)
            else obj_in.model_dump(exclude_unset=True)
        )

        # do not allow tenant_id or id to be updated
        update_data.pop("tenant_id", None)
        update_data.pop("id", None)

        for field, value in update_data.items():
            setattr(db_obj, field, value)

        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def remove(
        self, db: AsyncSession, *, id: UUID, tenant_id: UUID
    ) -> ModelType | None:
        """Delete a record, strictly filtered by tenant_id."""
        db_obj = await self.get(db=db, id=id, tenant_id=tenant_id)
        if not db_obj:
            return None  # TODO: consider raising an exception here instead for better error handling

        await db.delete(db_obj)
        await db.commit()
        return db_obj
