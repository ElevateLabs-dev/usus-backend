from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.base_crud import CRUDBaseRoot
from src.domains.tenants.models import Tenant
from src.domains.tenants.schemas import TenantCreate, TenantUpdate


class CRUDTenant(CRUDBaseRoot[Tenant, TenantCreate, TenantUpdate]):
    async def list_active(self, db: AsyncSession) -> list[Tenant]:
        result = await db.execute(
            select(self.model)
            .where(self.model.is_active == True)  # noqa: E712
            .order_by(self.model.name)
        )
        return list(result.scalars().all())


tenant = CRUDTenant(Tenant)
