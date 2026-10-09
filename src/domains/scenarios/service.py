import uuid
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.training import (
    CATEGORY_INFO,
    TrainingCategory,
    category_name,
    dimension_name,
)
from src.domains.evaluations.models import EvaluationResult
from src.domains.scenarios.crud import CRUDScenario
from src.domains.scenarios.defaults import DEFAULT_SCENARIOS
from src.domains.scenarios.models import DifficultyLevel, Scenario
from src.domains.scenarios.schemas import (
    CategoryRef,
    CategoryResponse,
    CustomerProfile,
    ScenarioBrief,
    ScenarioProgress,
    ScenarioSummary,
    SkillRef,
)
from src.domains.simulations.models import Session, SessionStatus

_DIFFICULTY_ORDER = {
    DifficultyLevel.BEGINNER: 0,
    DifficultyLevel.INTERMEDIATE: 1,
    DifficultyLevel.ADVANCED: 2,
}


class ScenarioService:
    def __init__(self, repository: CRUDScenario):
        self.repository = repository

    async def get_scenario_by_id(
        self, db: AsyncSession, tenant_id: uuid.UUID, scenario_id: uuid.UUID
    ) -> Scenario | None:
        return await self.repository.get(db=db, id=scenario_id, tenant_id=tenant_id)

    async def list_all_scenarios(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        category: TrainingCategory | None = None,
        difficulty: DifficultyLevel | None = None,
    ) -> Sequence[Scenario]:
        query = select(Scenario).where(Scenario.tenant_id == tenant_id)
        if category is not None:
            query = query.where(Scenario.category == category.value)
        if difficulty is not None:
            query = query.where(Scenario.difficulty == difficulty)
        scenarios = (await db.execute(query)).scalars().all()
        # Category, then Beginner -> Advanced, then name
        return sorted(
            scenarios,
            key=lambda s: (
                s.category or "~",
                _DIFFICULTY_ORDER.get(s.difficulty, 9),
                s.name,
            ),
        )

    async def list_categories(
        self, db: AsyncSession, tenant_id: uuid.UUID
    ) -> list[CategoryResponse]:
        result = await db.execute(
            select(Scenario.category, func.count(Scenario.id))
            .where(Scenario.tenant_id == tenant_id)
            .group_by(Scenario.category)
        )
        counts = {category: count for category, count in result.all()}
        return [
            CategoryResponse(
                id=category,
                name=name,
                description=description,
                scenario_count=counts.get(category.value, 0),
            )
            for category, (name, description) in CATEGORY_INFO.items()
        ]

    async def user_progress(
        self, db: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> dict[uuid.UUID, ScenarioProgress]:
        """The user's attempts / scores per scenario, from their sessions."""
        result = await db.execute(
            select(
                Session.scenario_id,
                Session.status,
                EvaluationResult.overall_score,
            )
            .outerjoin(EvaluationResult, EvaluationResult.session_id == Session.id)
            .where(Session.tenant_id == tenant_id, Session.user_id == user_id)
            .order_by(Session.created_at)
        )

        progress: dict[uuid.UUID, ScenarioProgress] = {}
        for scenario_id, status, score in result.all():
            entry = progress.setdefault(
                scenario_id,
                ScenarioProgress(
                    status="new", attempts=0, best_score=None, last_score=None
                ),
            )
            entry.attempts += 1
            if status == SessionStatus.IN_PROGRESS:
                entry.status = "in_progress"
            if score is not None:
                entry.last_score = score
                entry.best_score = max(entry.best_score or 0, score)
                if entry.status == "new":
                    entry.status = "completed"
        return progress

    @staticmethod
    def to_summary(
        scenario: Scenario, progress: ScenarioProgress | None
    ) -> ScenarioSummary:
        return ScenarioSummary(**_summary_fields(scenario, progress))

    @staticmethod
    def to_brief(
        scenario: Scenario, progress: ScenarioProgress | None
    ) -> ScenarioBrief:
        return ScenarioBrief(
            **_summary_fields(scenario, progress),
            customer=CustomerProfile(
                name=scenario.customer_name,
                personality=scenario.customer_personality,
                emotion=scenario.customer_emotion,
                background=scenario.customer_background,
            ),
            situation=scenario.situation,
            customer_goal=scenario.customer_goal,
            trainee_objective=scenario.trainee_objective,
            important_information=scenario.important_information or [],
        )

    async def seed_defaults(
        self, db: AsyncSession, tenant_id: uuid.UUID
    ) -> Sequence[Scenario]:
        """
        Make sure the organization has the starter scenarios.

        Creates any that are missing (matched by name) and fills in fields that
        are still empty on existing ones — never overwrites edited content.
        """
        for default in DEFAULT_SCENARIOS:
            existing = await self.repository.get_by_name(
                db=db, tenant_id=tenant_id, name=default.name
            )
            if existing is None:
                await self.repository.create(db=db, obj_in=default, tenant_id=tenant_id)
                continue

            changed = False
            for field, value in default.model_dump().items():
                if getattr(existing, field) in (None, "", []) and value not in (
                    None,
                    "",
                    [],
                ):
                    setattr(existing, field, value)
                    changed = True
            if changed:
                db.add(existing)
                await db.commit()

        return await self.list_all_scenarios(db, tenant_id)


def _summary_fields(scenario: Scenario, progress: ScenarioProgress | None) -> dict:
    category = (
        CategoryRef(id=scenario.category, name=category_name(scenario.category))
        if scenario.category
        else None
    )
    return {
        "id": scenario.id,
        "name": scenario.name,
        "description": scenario.description,
        "category": category,
        "difficulty": scenario.difficulty,
        "persona": scenario.persona,
        "skills": [
            SkillRef(id=skill, name=dimension_name(skill))
            for skill in scenario.skills or []
        ],
        "estimated_minutes": scenario.estimated_minutes,
        "progress": progress
        or ScenarioProgress(status="new", attempts=0, best_score=None, last_score=None),
    }
