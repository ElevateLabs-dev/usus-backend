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
    ScenarioPatch,
    ScenarioProgress,
    ScenarioSummary,
    ScenarioWrite,
    SkillRef,
)
from src.domains.simulations.models import Session

_DIFFICULTY_ORDER = {
    DifficultyLevel.BEGINNER: 0,
    DifficultyLevel.INTERMEDIATE: 1,
    DifficultyLevel.ADVANCED: 2,
}


_REQUIRED_FIELDS = {
    "name",
    "description",
    "difficulty",
    "persona",
    "skills",
    "estimated_minutes",
    "important_information",
    "is_archived",
}


# A scenario counts as passed (and towards unlocking the next level) once the
# trainee's best overall score reaches this.
PASS_SCORE = 60

_LEVELS = [
    DifficultyLevel.BEGINNER,
    DifficultyLevel.INTERMEDIATE,
    DifficultyLevel.ADVANCED,
]

_LEVEL_NAMES = {
    DifficultyLevel.BEGINNER: "Beginner",
    DifficultyLevel.INTERMEDIATE: "Intermediate",
    DifficultyLevel.ADVANCED: "Advanced",
}


class ScenarioNameTakenError(Exception):
    """The organization already has a scenario with this name."""


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
        include_archived: bool = False,
    ) -> Sequence[Scenario]:
        query = select(Scenario).where(Scenario.tenant_id == tenant_id)
        if not include_archived:
            query = query.where(Scenario.is_archived.is_(False))
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
            .where(Scenario.tenant_id == tenant_id, Scenario.is_archived.is_(False))
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
            if score is not None:
                entry.last_score = score
                entry.best_score = max(entry.best_score or 0, score)

        for entry in progress.values():
            passed = (entry.best_score or 0) >= PASS_SCORE
            entry.status = "completed" if passed else "in_progress"
        return progress

    async def locked_levels(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        progress: dict[uuid.UUID, ScenarioProgress],
    ) -> dict[DifficultyLevel, str]:
        """
        The levels a trainee cannot start yet, each with the reason.

        Beginner is always open. Each next level opens once every active
        scenario of the level before it is passed (an empty level counts as
        passed).
        """
        scenarios = await self.list_all_scenarios(db, tenant_id)
        locked: dict[DifficultyLevel, str] = {}
        for previous, level in zip(_LEVELS, _LEVELS[1:]):
            unpassed = [
                s
                for s in scenarios
                if s.difficulty == previous
                and (progress.get(s.id) is None or progress[s.id].status != "completed")
            ]
            if previous in locked or unpassed:
                locked[level] = (
                    f"Pass every {_LEVEL_NAMES[previous]} scenario (score "
                    f"{PASS_SCORE}% or more) to unlock {_LEVEL_NAMES[level]}."
                )
        return locked

    @staticmethod
    def to_summary(
        scenario: Scenario,
        progress: ScenarioProgress | None,
        locked_reason: str | None = None,
    ) -> ScenarioSummary:
        return ScenarioSummary(**_summary_fields(scenario, progress, locked_reason))

    @staticmethod
    def to_brief(
        scenario: Scenario,
        progress: ScenarioProgress | None,
        locked_reason: str | None = None,
    ) -> ScenarioBrief:
        return ScenarioBrief(
            **_summary_fields(scenario, progress, locked_reason),
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

    async def create_scenario(
        self, db: AsyncSession, tenant_id: uuid.UUID, data: ScenarioWrite
    ) -> Scenario:
        """Raises ScenarioNameTakenError if the organization already has the name."""
        if await self.repository.get_by_name(db, tenant_id, data.name.strip()):
            raise ScenarioNameTakenError(data.name)
        scenario = Scenario(
            **{**data.model_dump(), "name": data.name.strip()}, tenant_id=tenant_id
        )
        db.add(scenario)
        await db.commit()
        await db.refresh(scenario)
        return scenario

    async def update_scenario(
        self, db: AsyncSession, scenario: Scenario, data: ScenarioPatch
    ) -> Scenario:
        """Apply only the fields that were sent."""
        # An explicit null clears optional text fields but is ignored for
        # fields the database requires.
        changes = {
            field: value
            for field, value in data.model_dump(exclude_unset=True).items()
            if value is not None or field not in _REQUIRED_FIELDS
        }
        new_name = (changes.get("name") or "").strip()
        if new_name and new_name != scenario.name:
            if await self.repository.get_by_name(db, scenario.tenant_id, new_name):
                raise ScenarioNameTakenError(new_name)
            changes["name"] = new_name
        for field, value in changes.items():
            setattr(scenario, field, value)
        db.add(scenario)
        await db.commit()
        await db.refresh(scenario)
        return scenario

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
            if existing.is_archived:
                continue  # the organization retired this one; leave it alone

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


def _summary_fields(
    scenario: Scenario,
    progress: ScenarioProgress | None,
    locked_reason: str | None = None,
) -> dict:
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
        "locked": locked_reason is not None,
        "locked_reason": locked_reason,
    }
