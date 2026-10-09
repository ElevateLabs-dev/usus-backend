import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.scenarios.crud import CRUDScenario
from src.domains.scenarios.prompts import build_customer_prompt
from src.domains.simulations.crud import (
    CRUDMessage,
    CRUDSession,
)
from src.domains.simulations.models import (
    Message,
    MessageRole,
    Session,
    SessionStatus,
)
from src.domains.simulations.schemas import (
    MessageCreate,
    SessionCreate,
    SessionUpdate,
)
from src.infrastructure.llm.base import LLMProvider


class SimulationService:
    def __init__(
        self,
        session_repo: CRUDSession,
        message_repo: CRUDMessage,
        scenario_repo: CRUDScenario,
        llm_provider: LLMProvider,
    ):
        self.session_repo = session_repo
        self.message_repo = message_repo
        self.scenario_repo = scenario_repo
        self.llm_provider = llm_provider

    async def start_session(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        scenario_id: uuid.UUID,
    ) -> Session:
        scenario = await self.scenario_repo.get(
            db=db,
            id=scenario_id,
            tenant_id=tenant_id,
        )

        if not scenario:
            raise ValueError("Scenario not found")

        session_in = SessionCreate(
            user_id=user_id,
            scenario_id=scenario_id,
            status=SessionStatus.IN_PROGRESS,
        )

        session = await self.session_repo.create(
            db=db,
            obj_in=session_in,
            tenant_id=tenant_id,
        )

        system_prompt_content = build_customer_prompt(scenario)

        sys_msg_in = MessageCreate(
            session_id=session.id,
            role=MessageRole.SYSTEM,
            content=system_prompt_content,
        )

        await self.message_repo.create(
            db=db,
            obj_in=sys_msg_in,
            tenant_id=tenant_id,
        )

        return session

    async def send_message(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        session_id: uuid.UUID,
        user_text: str,
    ) -> Message:
        session = await self.session_repo.get(
            db=db,
            id=session_id,
            tenant_id=tenant_id,
        )

        if not session or session.status != SessionStatus.IN_PROGRESS:
            raise ValueError("Session is not active or not found")

        user_msg_in = MessageCreate(
            session_id=session_id,
            role=MessageRole.USER,
            content=user_text,
        )

        await self.message_repo.create(
            db=db,
            obj_in=user_msg_in,
            tenant_id=tenant_id,
        )

        session_msgs = await self.message_repo.get_by_session(
            db=db,
            tenant_id=tenant_id,
            session_id=session_id,
        )

        system_prompt = next(
            (
                message.content
                for message in session_msgs
                if message.role == MessageRole.SYSTEM
            ),
            "",
        )

        llm_messages = [
            {
                "role": message.role.value,
                "content": message.content,
            }
            for message in session_msgs
            if message.role != MessageRole.SYSTEM
        ]

        response_text = await self.llm_provider.generate_response(
            system_prompt=system_prompt,
            messages=llm_messages,
        )

        model_msg_in = MessageCreate(
            session_id=session_id,
            role=MessageRole.MODEL,
            content=response_text,
        )

        model_msg = await self.message_repo.create(
            db=db,
            obj_in=model_msg_in,
            tenant_id=tenant_id,
        )

        return model_msg

    async def end_session(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> Session:
        """
        End the simulation immediately.

        Evaluation is intentionally not performed here.
        The router queues the background evaluation task after
        the session is marked as COMPLETED.
        """

        session = await self.session_repo.get(
            db=db,
            id=session_id,
            tenant_id=tenant_id,
        )

        if not session:
            raise ValueError("Session not found")

        # Already ended: safe to call again (the router re-queues the
        # evaluation for a COMPLETED session, which retries a failed one).
        if session.status in (SessionStatus.COMPLETED, SessionStatus.EVALUATED):
            return session

        if session.status != SessionStatus.IN_PROGRESS:
            raise ValueError("Session is not active")

        session_update = SessionUpdate(
            status=SessionStatus.COMPLETED,
            ended_at=datetime.now(timezone.utc),
        )

        updated_session = await self.session_repo.update(
            db=db,
            id=session.id,
            obj_in=session_update,
            tenant_id=tenant_id,
        )

        if updated_session is None:
            raise ValueError("Failed to update session status to COMPLETED")

        return updated_session
