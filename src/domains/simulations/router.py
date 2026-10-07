from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import (
    AuthContext,
    get_auth_context,
    get_current_tenant_id,
)
from src.celery_app import celery_app

from src.domains.evaluations.crud import (
    evaluation_result as eval_result_repo,
)
from src.domains.evaluations.schemas import (
    EvaluationResultDetailResponse,
)

from src.domains.scenarios.crud import scenario as scenario_repo

from src.domains.simulations.crud import (
    message as message_repo,
    session as session_repo,
)

from src.domains.simulations.models import MessageRole

from src.domains.simulations.schemas import (
    SendMessageRequest,
    SendMessageResponse,
    SessionResponse,
    StartSessionRequest,
)

from src.domains.simulations.service import SimulationService

from src.infrastructure.llm.ollama_provider import OllamaProvider


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

_llm = OllamaProvider()

_simulation_service = SimulationService(
    session_repo=session_repo,
    message_repo=message_repo,
    scenario_repo=scenario_repo,
    llm_provider=_llm,
)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(
    prefix="/api/v1/simulations",
    tags=["Simulations"],
)


@router.get("/health")
async def simulation_health_check():
    return {
        "status": "ok",
        "domain": "simulations",
    }


@router.post(
    "/start",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_simulation(
    body: StartSessionRequest,
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    tenant_id: Annotated[UUID, Depends(get_current_tenant_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        session = await _simulation_service.start_session(
            db=db,
            user_id=ctx.user_id,
            tenant_id=tenant_id,
            scenario_id=body.scenario_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    return session


@router.post(
    "/{session_id}/message",
    response_model=SendMessageResponse,
    status_code=status.HTTP_200_OK,
)
async def send_message(
    session_id: UUID,
    body: SendMessageRequest,
    tenant_id: Annotated[UUID, Depends(get_current_tenant_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        ai_reply = await _simulation_service.send_message(
            db=db,
            tenant_id=tenant_id,
            session_id=session_id,
            user_text=body.content,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    all_messages = await message_repo.get_by_session(
        db=db,
        tenant_id=tenant_id,
        session_id=session_id,
    )

    conversation_messages = [
        message
        for message in all_messages
        if message.role != MessageRole.SYSTEM
    ]

    if len(conversation_messages) < 2:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Conversation messages could not be retrieved.",
        )

    user_message = conversation_messages[-2]

    return SendMessageResponse(
        user_message=user_message,
        ai_reply=ai_reply,
    )


@router.post(
    "/{session_id}/end",
    response_model=SessionResponse,
    status_code=status.HTTP_200_OK,
)
async def end_simulation(
    session_id: UUID,
    tenant_id: Annotated[UUID, Depends(get_current_tenant_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        completed_session = await _simulation_service.end_session(
            db=db,
            tenant_id=tenant_id,
            session_id=session_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    # Evaluation is intentionally queued in the background.
    # The API returns immediately instead of waiting for the LLM.
    celery_app.send_task(
        "src.domains.evaluations.tasks.generate_evaluation_report",
        args=[
            str(session_id),
            str(tenant_id),
        ],
    )

    return completed_session


@router.get(
    "/{session_id}/evaluation",
    response_model=EvaluationResultDetailResponse,
    status_code=status.HTTP_200_OK,
)
async def get_evaluation(
    session_id: UUID,
    tenant_id: Annotated[UUID, Depends(get_current_tenant_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    evaluation = await eval_result_repo.get_by_session_with_details(
        db=db,
        tenant_id=tenant_id,
        session_id=session_id,
    )

    if evaluation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation not found for this session.",
        )

    return evaluation