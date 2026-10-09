from uuid import UUID
from typing import Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.core.training import SkillDimension
from src.core.base_crud import CRUDBase, CRUDBaseRoot
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
        evaluation = result.scalar_one_or_none()
        if evaluation is not None:
            # Always return dimensions in the catalog's fixed order
            order = {d.value: i for i, d in enumerate(SkillDimension)}
            evaluation.dimension_scores.sort(
                key=lambda d: order.get(d.dimension_key or "", len(order))
            )
        return evaluation


class CRUDDimensionScore(CRUDBaseRoot[DimensionScore, DimensionScoreCreate, DimensionScoreUpdate]):
    pass


class CRUDRedFlag(CRUDBaseRoot[RedFlag, RedFlagCreate, RedFlagUpdate]):
    pass


evaluation_result = CRUDEvaluationResult(EvaluationResult)
dimension_score = CRUDDimensionScore(DimensionScore)
red_flag = CRUDRedFlag(RedFlag)
