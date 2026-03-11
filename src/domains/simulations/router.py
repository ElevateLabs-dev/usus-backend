from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_current_tenant_id
from src.domains.evaluations.crud import evaluation_result as eval_result_repo
from src.domains.evaluations.crud import dimension_score as dimension_score_repo
from src.domains.evaluations.crud import red_flag as red_flag_repo
from src.domains.evaluations.schemas import EvaluationResultDetailResponse
from src.domains.evaluations.service import EvaluationService
from src.domains.scenarios.crud import scenario as scenario_repo
from src.domains.simulations.crud import (
    session as session_repo,
    message as message_repo,
)
from src.domains.simulations.schemas import (
    EndSessionResponse,
    SendMessageRequest,
    SendMessageResponse,
    SessionResponse,
    StartSessionRequest,
)
from src.domains.simulations.service import SimulationService
from src.infrastructure.llm.anthropic import AnthropicProvider

# ---------------------------------------------------------------------------
# Service singletons — stateless, safe to share across requests
# ---------------------------------------------------------------------------
_llm = AnthropicProvider()
_eval_service = EvaluationService(
    eval_result_repo=eval_result_repo,
    dimension_score_repo=dimension_score_repo,
    red_flag_repo=red_flag_repo,
    llm_provider=_llm,
)
_simulation_service = SimulationService(
    session_repo=session_repo,
    message_repo=message_repo,
    scenario_repo=scenario_repo,
    llm_provider=_llm,
    evaluation_service=_eval_service,
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
    return {"status": "ok", "domain": "simulations"}


@router.post(
    "/start", response_model=SessionResponse, status_code=status.HTTP_201_CREATED
)
async def start_simulation(
    body: StartSessionRequest,
    tenant_id: Annotated[UUID, Depends(get_current_tenant_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        session = await _simulation_service.start_session(
            db=db, tenant_id=tenant_id, scenario_id=body.scenario_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    # The user message is the second-to-last message; retrieve the full ordered list
    # and return the last two entries (user, then AI reply).
    all_messages = await message_repo.get_by_session(
        db=db, tenant_id=tenant_id, session_id=session_id
    )
    # Filter to conversation messages only (exclude system prompt)
    from src.domains.simulations.models import MessageRole

    conv_messages = [m for m in all_messages if m.role != MessageRole.SYSTEM]
    user_message = conv_messages[-2]  # second-to-last after AI reply was appended

    return SendMessageResponse(user_message=user_message, ai_reply=ai_reply)


@router.post(
    "/{session_id}/end",
    response_model=EndSessionResponse,
    status_code=status.HTTP_200_OK,
)
async def end_simulation(
    session_id: UUID,
    tenant_id: Annotated[UUID, Depends(get_current_tenant_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        ended_session, _ = await _simulation_service.end_session(
            db=db, tenant_id=tenant_id, session_id=session_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    evaluation = await eval_result_repo.get_by_session_with_details(
        db=db, tenant_id=tenant_id, session_id=session_id
    )
    if evaluation is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Evaluation was not generated.",
        )

    return EndSessionResponse(session=ended_session, evaluation=evaluation)


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
        db=db, tenant_id=tenant_id, session_id=session_id
    )
    if evaluation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation not found for this session.",
        )
    return evaluation
