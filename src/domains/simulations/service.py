import uuid
from typing import Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from src.infrastructure.llm.base import LLMProvider
from src.domains.simulations.models import Session, Message, SessionStatus, MessageRole
from src.domains.simulations.schemas import SessionCreate, SessionUpdate, MessageCreate
from src.domains.simulations.crud import CRUDSession, CRUDMessage
from src.domains.scenarios.crud import CRUDScenario
from src.domains.evaluations.service import EvaluationService
from src.domains.evaluations.models import EvaluationResult


class SimulationService:
    def __init__(
        self,
        session_repo: CRUDSession,
        message_repo: CRUDMessage,
        scenario_repo: CRUDScenario,
        llm_provider: LLMProvider,
        evaluation_service: EvaluationService,
    ):
        self.session_repo = session_repo
        self.message_repo = message_repo
        self.scenario_repo = scenario_repo
        self.llm_provider = llm_provider
        self.evaluation_service = evaluation_service

    async def start_session(
        self, db: AsyncSession, tenant_id: uuid.UUID, scenario_id: uuid.UUID
    ) -> Session:
        scenario = await self.scenario_repo.get(
            db=db, id=scenario_id, tenant_id=tenant_id
        )
        if not scenario:
            raise ValueError("Scenario not found")

        session_in = SessionCreate(
            scenario_id=scenario_id, status=SessionStatus.IN_PROGRESS
        )
        session = await self.session_repo.create(
            db=db, obj_in=session_in, tenant_id=tenant_id
        )

        sys_msg_in = MessageCreate(
            session_id=session.id,
            role=MessageRole.SYSTEM,
            content=f"You are a {scenario.persona.value} customer. Scenario: {scenario.name}. {scenario.description}",
        )
        await self.message_repo.create(db=db, obj_in=sys_msg_in, tenant_id=tenant_id)

        return session

    async def send_message(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        session_id: uuid.UUID,
        user_text: str,
    ) -> Message:
        session = await self.session_repo.get(db=db, id=session_id, tenant_id=tenant_id)
        if not session or session.status != SessionStatus.IN_PROGRESS:
            raise ValueError("Session is not active or not found")

        user_msg_in = MessageCreate(
            session_id=session_id,
            role=MessageRole.USER,
            content=user_text,
        )
        await self.message_repo.create(db=db, obj_in=user_msg_in, tenant_id=tenant_id)

        session_msgs = await self.message_repo.get_by_session(
            db=db, tenant_id=tenant_id, session_id=session_id
        )

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

        model_msg_in = MessageCreate(
            session_id=session_id,
            role=MessageRole.MODEL,
            content=response_text,
        )
        model_msg = await self.message_repo.create(
            db=db, obj_in=model_msg_in, tenant_id=tenant_id
        )
        return model_msg

    async def end_session(
        self, db: AsyncSession, tenant_id: uuid.UUID, session_id: uuid.UUID
    ) -> Tuple[Session, EvaluationResult]:
        session = await self.session_repo.get(db=db, id=session_id, tenant_id=tenant_id)
        if not session:
            raise ValueError("Session not found")

        session_update = SessionUpdate(status=SessionStatus.COMPLETED)
        updated_session = await self.session_repo.update(
            db=db, id=session.id, obj_in=session_update, tenant_id=tenant_id
        )
        if updated_session is None:
            raise ValueError("Failed to update session status to COMPLETED")
        session = updated_session

        all_msgs = await self.message_repo.get_by_session(
            db=db, tenant_id=tenant_id, session_id=session_id
        )
        session_msgs = [m for m in all_msgs if m.role != MessageRole.SYSTEM]

        eval_result = await self.evaluation_service.evaluate_session(
            db, tenant_id, session, session_msgs
        )

        # Mark as evaluated
        session_update = SessionUpdate(status=SessionStatus.EVALUATED)
        evaluated_session = await self.session_repo.update(
            db=db, id=session.id, obj_in=session_update, tenant_id=tenant_id
        )

        if evaluated_session is None:
            raise ValueError("Failed to update session status to EVALUATED")

        return evaluated_session, eval_result
