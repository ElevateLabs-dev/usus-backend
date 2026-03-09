import uuid
from typing import List

from src.infrastructure.storage.memory import MemoryRepository
from src.infrastructure.llm.base import LLMProvider
from src.domains.scenarios.models import Scenario
from src.domains.simulations.models import Session, Message, SessionStatus, MessageRole
from src.domains.evaluations.service import EvaluationService


class SimulationService:
    def __init__(
        self,
        session_repo: MemoryRepository[Session],
        message_repo: MemoryRepository[Message],
        scenario_repo: MemoryRepository[Scenario],
        llm_provider: LLMProvider,
        evaluation_service: EvaluationService,
    ):
        self.session_repo = session_repo
        self.message_repo = message_repo
        self.scenario_repo = scenario_repo
        self.llm_provider = llm_provider
        self.evaluation_service = evaluation_service

    def start_session(self, tenant_id: uuid.UUID, scenario_id: uuid.UUID) -> Session:
        scenario = self.scenario_repo.get(tenant_id, scenario_id)
        if not scenario:
            raise ValueError("Scenario not found")

        session = Session(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            scenario_id=scenario_id,
            status=SessionStatus.IN_PROGRESS,
        )
        self.session_repo.save(tenant_id, session)

        sys_msg = Message(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            session_id=session.id,
            role=MessageRole.SYSTEM,
            content=f"You are a {scenario.persona.value} customer. Scenario: {scenario.name}. {scenario.description}",
        )
        self.message_repo.save(tenant_id, sys_msg)

        return session

    async def send_message(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID, user_text: str
    ) -> Message:
        session = self.session_repo.get(tenant_id, session_id)
        if not session or session.status != SessionStatus.IN_PROGRESS:
            raise ValueError("Session is not active or not found")

        user_msg = Message(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            session_id=session_id,
            role=MessageRole.USER,
            content=user_text,
        )
        self.message_repo.save(tenant_id, user_msg)

        # Get all messages
        all_msgs = self.message_repo.list_all(tenant_id)
        session_msgs = [m for m in all_msgs if m.session_id == session_id]

        system_prompt = next(
            (m.content for m in session_msgs if m.role == MessageRole.SYSTEM), ""
        )
        llm_messages = [
            {"role": m.role.value, "content": m.content}
            for m in session_msgs
            if m.role != MessageRole.SYSTEM
        ]

        response_text = await self.llm_provider.generate_response(
            system_prompt=system_prompt, messages=llm_messages
        )

        model_msg = Message(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            session_id=session_id,
            role=MessageRole.MODEL,
            content=response_text,
        )
        self.message_repo.save(tenant_id, model_msg)
        return model_msg

    async def end_session(self, tenant_id: uuid.UUID, session_id: uuid.UUID):
        session = self.session_repo.get(tenant_id, session_id)
        if not session:
            raise ValueError("Session not found")

        session.status = SessionStatus.COMPLETED
        self.session_repo.save(tenant_id, session)

        all_msgs = self.message_repo.list_all(tenant_id)
        session_msgs = [
            m
            for m in all_msgs
            if m.session_id == session_id and m.role != MessageRole.SYSTEM
        ]

        eval_result = await self.evaluation_service.evaluate_session(
            tenant_id, session, session_msgs
        )
        self.session_repo.save(tenant_id, session)

        return session, eval_result
