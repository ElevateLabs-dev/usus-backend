from uuid import UUID
from typing import Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.core.base_crud import CRUDBase
from src.domains.evaluations.models import EvaluationResult, DimensionScore, RedFlag
from src.domains.evaluations.schemas import (
    EvaluationResultCreate,
    EvaluationResultUpdate,
    DimensionScoreCreate,
    DimensionScoreUpdate,
    RedFlagCreate,
    RedFlagUpdate,
)


class CRUDEvaluationResult(
    CRUDBase[EvaluationResult, EvaluationResultCreate, EvaluationResultUpdate]
):
    async def get_by_session(
        self, db: AsyncSession, tenant_id: UUID, session_id: UUID
    ) -> EvaluationResult | None:
        query = select(self.model).where(
            self.model.tenant_id == tenant_id, self.model.session_id == session_id
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_session_with_details(
        self, db: AsyncSession, tenant_id: UUID, session_id: UUID
    ) -> EvaluationResult | None:
        query = (
            select(self.model)
            .where(
                self.model.tenant_id == tenant_id, self.model.session_id == session_id
            )
            .options(
                selectinload(self.model.dimension_scores),
                selectinload(self.model.red_flags),
            )
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()


# DimensionScore and RedFlag inherit from Base, not TenantAwareBase, but usually
# accessed via EvaluationResult. If we need direct CRUD, we must ensure we check the
# parent's tenant_id, or trust the app layer. For now, we provide base CRUD but
# without tenant_id enforcement if they don't have it, or we join with parent.
# Since they don't have tenant_id in the model schema, standard CRUDBase might fail
# because it assumes `self.model.tenant_id` exists. Let's create custom ones.


class CRUDDimensionScore:
    def __init__(self, model: type[DimensionScore]):
        self.model = model

    async def create(
        self, db: AsyncSession, *, obj_in: DimensionScoreCreate
    ) -> DimensionScore:
        db_obj = self.model(**obj_in.model_dump())
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj


class CRUDRedFlag:
    def __init__(self, model: type[RedFlag]):
        self.model = model

    async def create(self, db: AsyncSession, *, obj_in: RedFlagCreate) -> RedFlag:
        db_obj = self.model(**obj_in.model_dump())
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj


evaluation_result = CRUDEvaluationResult(EvaluationResult)
dimension_score = CRUDDimensionScore(DimensionScore)
red_flag = CRUDRedFlag(RedFlag)
