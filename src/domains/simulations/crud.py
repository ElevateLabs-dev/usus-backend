from uuid import UUID
from typing import Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.core.base_crud import CRUDBase
from src.domains.simulations.models import Session, Message
from src.domains.simulations.schemas import SessionCreate, SessionUpdate, MessageCreate, MessageUpdate


class CRUDSession(CRUDBase[Session, SessionCreate, SessionUpdate]):
    async def get_with_messages(
        self, db: AsyncSession, tenant_id: UUID, id: UUID
    ) -> Session | None:
        query = select(self.model).where(
            self.model.tenant_id == tenant_id, self.model.id == id
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()


class CRUDMessage(CRUDBase[Message, MessageCreate, MessageUpdate]):
    async def get_by_session(
        self, db: AsyncSession, tenant_id: UUID, session_id: UUID
    ) -> Sequence[Message]:
        query = (
            select(self.model)
            .where(self.model.tenant_id == tenant_id, self.model.session_id == session_id)
            .order_by(self.model.created_at.asc())
        )
        result = await db.execute(query)
        return result.scalars().all()


session = CRUDSession(Session)
message = CRUDMessage(Message)
