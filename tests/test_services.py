import pytest
import pytest_asyncio
import uuid
import json

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from src.core.base_model import Base

from src.infrastructure.llm.base import LLMProvider
from src.domains.scenarios.models import Scenario
from src.domains.scenarios.crud import CRUDScenario
from src.domains.scenarios.service import ScenarioService

from src.domains.simulations.models import Session, Message, SessionStatus, MessageRole
from src.domains.simulations.crud import CRUDSession, CRUDMessage
from src.domains.simulations.service import SimulationService

from src.domains.evaluations.models import EvaluationResult, DimensionScore, RedFlag
from src.domains.evaluations.crud import (
    CRUDEvaluationResult,
    CRUDDimensionScore,
    CRUDRedFlag,
)
from src.domains.evaluations.service import EVALUATION_DIMENSIONS, EvaluationService

# It is important to import all models so Base.metadata knows about them
import src.domains.tenants.models


class MockLLMProvider(LLMProvider):
    async def generate_response(
        self, system_prompt, messages, temperature=0.7, max_tokens=1024, json_mode=False
    ):
        # Determine based on prompt if it's customer response or evaluation
        if "expert customer service evaluator" in system_prompt:
            return json.dumps(
                {
                    "overall_score": 90,
                    "summary": "Great job handling the customer.",
                    "dimensions": [
                        {"name": name, "score": 9, "rationale": "Well handled"}
                        for name in EVALUATION_DIMENSIONS
                    ],
                    "red_flags": [],
                }
            )
        else:
            return "I am a mock response from the customer."


@pytest_asyncio.fixture
async def db_session():
    # Use an in-memory SQLite database for tests
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def tenant_id():
    return uuid.uuid4()


@pytest.fixture
def scenario_service():
    repo = CRUDScenario(Scenario)
    return ScenarioService(repo)


@pytest.fixture
def evaluation_service():
    er_repo = CRUDEvaluationResult(EvaluationResult)
    ds_repo = CRUDDimensionScore(DimensionScore)
    rf_repo = CRUDRedFlag(RedFlag)
    llm = MockLLMProvider()
    return EvaluationService(er_repo, ds_repo, rf_repo, llm)


@pytest.fixture
def simulation_service(scenario_service, evaluation_service):
    session_repo = CRUDSession(Session)
    message_repo = CRUDMessage(Message)
    return SimulationService(
        session_repo,
        message_repo,
        scenario_service.repository,
        MockLLMProvider(),
    )


@pytest.mark.asyncio
async def test_scenario_service_seed(db_session, scenario_service, tenant_id):
    scenarios = await scenario_service.seed_defaults(db_session, tenant_id)
    assert len(scenarios) == 3

    # Second time should return the same
    scenarios2 = await scenario_service.seed_defaults(db_session, tenant_id)
    assert len(scenarios2) == 3


@pytest.mark.asyncio
async def test_full_simulation_loop(
    db_session, scenario_service, simulation_service, evaluation_service, tenant_id
):
    scenarios = await scenario_service.seed_defaults(db_session, tenant_id)
    scenario_id = scenarios[0].id

    # Start Session
    user_id = uuid.uuid4()
    session = await simulation_service.start_session(
        db_session, user_id=user_id, tenant_id=tenant_id, scenario_id=scenario_id
    )
    assert session.status == SessionStatus.IN_PROGRESS
    assert session.user_id == user_id

    # Send Message
    model_msg = await simulation_service.send_message(
        db_session, tenant_id, session.id, "Hello, how can I help?"
    )
    assert model_msg.role == MessageRole.MODEL
    assert model_msg.content == "I am a mock response from the customer."

    # End Session: marks it completed; evaluation runs separately (Celery task)
    completed = await simulation_service.end_session(db_session, tenant_id, session.id)
    assert completed.status == SessionStatus.COMPLETED

    messages = await CRUDMessage(Message).get_by_session(
        db_session, tenant_id, session.id
    )
    eval_result = await evaluation_service.evaluate_session(
        db=db_session,
        tenant_id=tenant_id,
        session=completed,
        messages=[m for m in messages if m.role != MessageRole.SYSTEM],
    )
    assert eval_result.overall_score == 90
    assert eval_result.summary == "Great job handling the customer."
