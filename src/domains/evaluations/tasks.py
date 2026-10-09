import asyncio
import uuid

from src.celery_app import celery_app
from src.core.database import AsyncSessionLocal

from src.domains.evaluations.crud import (
    dimension_score as dimension_score_repo,
    evaluation_result as eval_result_repo,
    red_flag as red_flag_repo,
)
from src.domains.evaluations.service import EvaluationService

from src.domains.simulations.crud import (
    message as message_repo,
    session as session_repo,
)

from src.domains.simulations.models import (
    MessageRole,
    SessionStatus,
)

from src.infrastructure.llm.factory import get_llm_provider


async def _generate_evaluation_report(
    simulation_id: str,
    tenant_id: str,
):
    session_id = uuid.UUID(simulation_id)
    tenant_uuid = uuid.UUID(tenant_id)

    llm_provider = get_llm_provider()

    evaluation_service = EvaluationService(
        eval_result_repo=eval_result_repo,
        dimension_score_repo=dimension_score_repo,
        red_flag_repo=red_flag_repo,
        llm_provider=llm_provider,
    )

    async with AsyncSessionLocal() as db:
        session = await session_repo.get(
            db=db,
            id=session_id,
            tenant_id=tenant_uuid,
        )

        if session is None:
            raise ValueError("Session not found")

        # Prevent duplicate evaluation.
        existing_evaluation = (
            await eval_result_repo.get_by_session_with_details(
                db=db,
                tenant_id=tenant_uuid,
                session_id=session_id,
            )
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
            raise ValueError(
                "Session must be completed before evaluation"
            )

        all_messages = await message_repo.get_by_session(
            db=db,
            tenant_id=tenant_uuid,
            session_id=session_id,
        )

        session_messages = [
            message
            for message in all_messages
            if message.role != MessageRole.SYSTEM
        ]

        if not session_messages:
            raise ValueError(
                "No conversation messages found for evaluation"
            )

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
            _generate_evaluation_report(
                simulation_id=simulation_id,
                tenant_id=tenant_id,
            )
        )

    except ValueError as exc:
        # These are validation/data errors rather than
        # temporary infrastructure failures.
        raise exc

    except Exception as exc:
        raise self.retry(
            exc=exc,
            countdown=10,
        )