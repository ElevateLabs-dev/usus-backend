import pytest
import uuid
import json

from src.infrastructure.storage.memory import MemoryRepository
from src.infrastructure.llm.base import LLMProvider
from src.domains.scenarios.models import Scenario
from src.domains.scenarios.service import ScenarioService
from src.domains.simulations.models import Session, Message, SessionStatus, MessageRole
from src.domains.simulations.service import SimulationService
from src.domains.evaluations.models import EvaluationResult, DimensionScore, RedFlag
from src.domains.evaluations.service import EvaluationService

class MockLLMProvider(LLMProvider):
    async def generate_response(self, system_prompt, messages, temperature=0.7, max_tokens=1024):
        # Determine based on prompt if it's customer response or evaluation
        if "expert customer service evaluator" in system_prompt:
            return json.dumps({
                "overall_score": 90,
                "summary": "Great job handling the customer.",
                "dimensions": [
                    {"name": "Empathy", "score": 9, "rationale": "Very empathetic"}
                ],
                "red_flags": []
            })
        else:
            return "I am a mock response from the customer."


@pytest.fixture
def tenant_id():
    return uuid.uuid4()


@pytest.fixture
def scenario_service():
    repo = MemoryRepository[Scenario]()
    return ScenarioService(repo)


@pytest.fixture
def evaluation_service():
    er_repo = MemoryRepository[EvaluationResult]()
    ds_repo = MemoryRepository[DimensionScore]()
    rf_repo = MemoryRepository[RedFlag]()
    llm = MockLLMProvider()
    return EvaluationService(er_repo, ds_repo, rf_repo, llm)


@pytest.fixture
def simulation_service(scenario_service, evaluation_service):
    session_repo = MemoryRepository[Session]()
    message_repo = MemoryRepository[Message]()
    return SimulationService(
        session_repo, 
        message_repo, 
        scenario_service.repository, 
        MockLLMProvider(),
        evaluation_service
    )


def test_scenario_service_seed(scenario_service, tenant_id):
    scenarios = scenario_service.seed_defaults(tenant_id)
    assert len(scenarios) == 3
    
    # Second time should return the same
    scenarios2 = scenario_service.seed_defaults(tenant_id)
    assert len(scenarios2) == 3


@pytest.mark.asyncio
async def test_full_simulation_loop(scenario_service, simulation_service, tenant_id):
    scenarios = scenario_service.seed_defaults(tenant_id)
    scenario_id = scenarios[0].id

    # Start Session
    session = simulation_service.start_session(tenant_id, scenario_id)
    assert session.status == SessionStatus.IN_PROGRESS
    
    # Send Message
    model_msg = await simulation_service.send_message(tenant_id, session.id, "Hello, how can I help?")
    assert model_msg.role == MessageRole.MODEL
    assert model_msg.content == "I am a mock response from the customer."

    # End Session
    updated_session, eval_result = await simulation_service.end_session(tenant_id, session.id)
    
    assert updated_session.status == SessionStatus.EVALUATED
    assert eval_result.overall_score == 90
    assert eval_result.summary == "Great job handling the customer."
