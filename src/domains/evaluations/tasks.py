import asyncio
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.celery_app import celery_app
from src.core.database import AsyncSessionLocal, engine
from src.domains.evaluations.crud import (
    dimension_score as dimension_score_repo,
)
from src.domains.evaluations.crud import (
    evaluation_result as eval_result_repo,
)
from src.domains.evaluations.crud import (
    red_flag as red_flag_repo,
)
from src.domains.evaluations.service import EvaluationService
from src.domains.simulations.crud import (
    message as message_repo,
)
from src.domains.simulations.crud import (
    session as session_repo,
)
from src.domains.simulations.models import (
    MessageRole,
    SessionStatus,
)
from src.infrastructure.llm.base import LLMProvider
from src.infrastructure.llm.factory import get_llm_provider

logger = logging.getLogger("usus.evaluations")


async def _generate_evaluation_report(
    simulation_id: str,
    tenant_id: str,
    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
    llm_provider: LLMProvider | None = None,
):
    session_id = uuid.UUID(simulation_id)
    tenant_uuid = uuid.UUID(tenant_id)

    llm_provider = llm_provider or get_llm_provider()

    evaluation_service = EvaluationService(
        eval_result_repo=eval_result_repo,
        dimension_score_repo=dimension_score_repo,
        red_flag_repo=red_flag_repo,
        llm_provider=llm_provider,
    )

    async with session_factory() as db:
        session = await session_repo.get(
            db=db,
            id=session_id,
            tenant_id=tenant_uuid,
        )

        if session is None:
            raise ValueError("Session not found")

        # Prevent duplicate evaluation.
        existing_evaluation = await eval_result_repo.get_by_session_with_details(
            db=db,
            tenant_id=tenant_uuid,
            session_id=session_id,
        )

        if existing_evaluation is not None:
            # Make sure the session reflects its actual state.
            if session.status != SessionStatus.EVALUATED:
                await session_repo.update(
                    db=db,
                    id=session.id,
                    obj_in={
                        "status": SessionStatus.EVALUATED,
                    },
                    tenant_id=tenant_uuid,
                )

            return {
                "simulation_id": simulation_id,
                "status": "already_evaluated",
            }

        # A session must be completed before evaluation starts.
        if session.status != SessionStatus.COMPLETED:
            raise ValueError("Session must be completed before evaluation")

        all_messages = await message_repo.get_by_session(
            db=db,
            tenant_id=tenant_uuid,
            session_id=session_id,
        )

        session_messages = [
            message for message in all_messages if message.role != MessageRole.SYSTEM
        ]

        # A session the trainee never replied in is still evaluated: the
        # evaluator scores it 0 without calling the LLM.

        await evaluation_service.evaluate_session(
            db=db,
            tenant_id=tenant_uuid,
            session=session,
            messages=session_messages,
        )

        # Evaluation completed successfully.
        updated_session = await session_repo.update(
            db=db,
            id=session.id,
            obj_in={
                "status": SessionStatus.EVALUATED,
            },
            tenant_id=tenant_uuid,
        )

        if updated_session is None:
            raise ValueError(
                "Evaluation was created but session status could not be updated"
            )

        return {
            "simulation_id": simulation_id,
            "status": "completed",
        }


async def _run_and_close_connections(simulation_id: str, tenant_id: str):
    """
    Each Celery task runs in a new event loop (asyncio.run), so pooled database
    connections from a previous task can't be reused: close them afterwards.
    """
    try:
        return await _generate_evaluation_report(
            simulation_id=simulation_id,
            tenant_id=tenant_id,
        )
    finally:
        await engine.dispose()


@celery_app.task(
    bind=True,
    max_retries=3,
)
def generate_evaluation_report(
    self,
    simulation_id: str,
    tenant_id: str,
):
    """
    Run the expensive AI evaluation in the background.

    The API request that ends the simulation does not wait
    for the LLM evaluation to finish.
    """
    try:
        return asyncio.run(
            _run_and_close_connections(
                simulation_id=simulation_id,
                tenant_id=tenant_id,
            )
        )

    except ValueError as exc:
        # These are validation/data errors rather than
        # temporary infrastructure failures.
        raise exc

    except Exception as exc:
        logger.warning(
            "Evaluation of session %s failed, retrying: %s", simulation_id, exc
        )
        raise self.retry(
            exc=exc,
            countdown=10,
        )
