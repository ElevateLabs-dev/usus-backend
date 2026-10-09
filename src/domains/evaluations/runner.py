"""
Runs a session's AI evaluation in the background, inside the API process
(FastAPI BackgroundTasks): the request that ends a session returns at once and
the trainee polls GET /simulations/{id}/evaluation for the result.
"""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.database import AsyncSessionLocal
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
from src.domains.simulations.models import MessageRole, SessionStatus
from src.infrastructure.llm.base import LLMProvider
from src.infrastructure.llm.factory import get_llm_provider

logger = logging.getLogger("usus.evaluations")

# Sessions being evaluated by this process, so a double "end" click does not
# start a second, duplicate evaluation.
_in_progress: set[uuid.UUID] = set()


async def run_evaluation(
    session_id: uuid.UUID,
    tenant_id: uuid.UUID,
    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
    llm_provider: LLMProvider | None = None,
) -> str:
    """
    Evaluate a completed session and save the result.

    Returns what happened ("completed", "already_evaluated", "skipped",
    "failed"). Never raises: failures are logged, the session stays
    `completed`, and ending the session again retries the evaluation.
    """
    if session_id in _in_progress:
        return "skipped"
    _in_progress.add(session_id)
    try:
        return await _evaluate(session_id, tenant_id, session_factory, llm_provider)
    except Exception:
        logger.exception("Evaluation of session %s failed", session_id)
        return "failed"
    finally:
        _in_progress.discard(session_id)


async def _evaluate(
    session_id: uuid.UUID,
    tenant_id: uuid.UUID,
    session_factory: async_sessionmaker[AsyncSession],
    llm_provider: LLMProvider | None,
) -> str:
    evaluation_service = EvaluationService(
        eval_result_repo=eval_result_repo,
        dimension_score_repo=dimension_score_repo,
        red_flag_repo=red_flag_repo,
        llm_provider=llm_provider or get_llm_provider(),
    )

    async with session_factory() as db:
        session = await session_repo.get(db=db, id=session_id, tenant_id=tenant_id)
        if session is None:
            logger.warning("Evaluation skipped: session %s not found", session_id)
            return "skipped"

        # Prevent duplicate evaluation.
        existing_evaluation = await eval_result_repo.get_by_session(
            db=db, tenant_id=tenant_id, session_id=session_id
        )
        if existing_evaluation is not None:
            # Make sure the session reflects its actual state.
            if session.status != SessionStatus.EVALUATED:
                await session_repo.update(
                    db=db,
                    id=session.id,
                    obj_in={"status": SessionStatus.EVALUATED},
                    tenant_id=tenant_id,
                )
            return "already_evaluated"

        # A session must be completed before evaluation starts.
        if session.status != SessionStatus.COMPLETED:
            logger.warning(
                "Evaluation skipped: session %s is %s, not completed",
                session_id,
                session.status.value,
            )
            return "skipped"

        all_messages = await message_repo.get_by_session(
            db=db, tenant_id=tenant_id, session_id=session_id
        )
        session_messages = [m for m in all_messages if m.role != MessageRole.SYSTEM]

        # Saves the evaluation and marks the session EVALUATED in one
        # transaction. A session the trainee never replied in is scored 0
        # without calling the LLM.
        await evaluation_service.evaluate_session(
            db=db,
            tenant_id=tenant_id,
            session=session,
            messages=session_messages,
        )
        return "completed"
