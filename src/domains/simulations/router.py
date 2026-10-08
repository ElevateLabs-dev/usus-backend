from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import AuthContext, get_auth_context
from src.domains.evaluations.crud import (
    dimension_score as dimension_score_repo,
)
from src.domains.evaluations.crud import (
    evaluation_result as eval_result_repo,
)
from src.domains.evaluations.crud import (
    red_flag as red_flag_repo,
)
from src.domains.evaluations.schemas import EvaluationResultDetailResponse
from src.domains.evaluations.service import EvaluationService
from src.domains.scenarios.crud import scenario as scenario_repo
from src.domains.simulations.crud import (
    message as message_repo,
)
from src.domains.simulations.crud import (
    session as session_repo,
)
from src.domains.simulations.models import MessageRole
from src.domains.simulations.schemas import (
    EndSessionResponse,
    SendMessageRequest,
    SendMessageResponse,
    SessionResponse,
    StartSessionRequest,
)
from src.domains.simulations.service import SimulationService
from src.infrastructure.llm.factory import get_llm_provider

# ---------------------------------------------------------------------------
# Service singletons — stateless, safe to share across requests
# ---------------------------------------------------------------------------

_llm = get_llm_provider()

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


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@router.get("/health")
async def simulation_health_check():
    return {
        "status": "ok",
        "domain": "simulations",
    }


# ---------------------------------------------------------------------------
# Start simulation
# ---------------------------------------------------------------------------


@router.post(
    "/start",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_simulation(
    body: StartSessionRequest,
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant context required",
        )

    try:
        session = await _simulation_service.start_session(
            db=db,
            user_id=ctx.user_id,
            tenant_id=ctx.tenant_id,
            scenario_id=body.scenario_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    return session


# ---------------------------------------------------------------------------
# Send message
# ---------------------------------------------------------------------------


@router.post(
    "/{session_id}/message",
    response_model=SendMessageResponse,
    status_code=status.HTTP_200_OK,
)
async def send_message(
    session_id: UUID,
    body: SendMessageRequest,
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant context required",
        )

    try:
        # Verify that this session belongs to the authenticated user.
        session = await session_repo.get(
            db=db,
            id=session_id,
            tenant_id=ctx.tenant_id,
        )

        if session is None:
            raise ValueError("Session not found")

        if session.user_id != ctx.user_id:
            raise ValueError("Session not found")

        ai_reply = await _simulation_service.send_message(
            db=db,
            tenant_id=ctx.tenant_id,
            session_id=session_id,
            user_text=body.content,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    # Retrieve the full ordered conversation.
    all_messages = await message_repo.get_by_session(
        db=db,
        tenant_id=ctx.tenant_id,
        session_id=session_id,
    )

    # Exclude the system prompt.
    conv_messages = [
        message for message in all_messages if message.role != MessageRole.SYSTEM
    ]

    if len(conv_messages) < 2:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Conversation messages could not be loaded.",
        )

    # AI reply has already been appended, so the previous message
    # is the trainee's message.
    user_message = conv_messages[-2]

    return SendMessageResponse(
        user_message=user_message,
        ai_reply=ai_reply,
    )


# ---------------------------------------------------------------------------
# End simulation
# ---------------------------------------------------------------------------


@router.post(
    "/{session_id}/end",
    response_model=EndSessionResponse,
    status_code=status.HTTP_200_OK,
)
async def end_simulation(
    session_id: UUID,
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant context required",
        )

    # Verify session ownership before allowing it to be ended/evaluated.
    session = await session_repo.get(
        db=db,
        id=session_id,
        tenant_id=ctx.tenant_id,
    )

    if session is None or session.user_id != ctx.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    try:
        ended_session, _ = await _simulation_service.end_session(
            db=db,
            tenant_id=ctx.tenant_id,
            session_id=session_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    evaluation = await eval_result_repo.get_by_session_with_details(
        db=db,
        tenant_id=ctx.tenant_id,
        session_id=session_id,
    )

    if evaluation is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Evaluation was not generated.",
        )

    return EndSessionResponse(
        session=ended_session,
        evaluation=evaluation,
    )


# ---------------------------------------------------------------------------
# Get evaluation
# ---------------------------------------------------------------------------


@router.get(
    "/{session_id}/evaluation",
    response_model=EvaluationResultDetailResponse,
    status_code=status.HTTP_200_OK,
)
async def get_evaluation(
    session_id: UUID,
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant context required",
        )

    # Verify that the evaluation belongs to a session owned
    # by the authenticated user.
    session = await session_repo.get(
        db=db,
        id=session_id,
        tenant_id=ctx.tenant_id,
    )

    if session is None or session.user_id != ctx.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation not found for this session.",
        )

    evaluation = await eval_result_repo.get_by_session_with_details(
        db=db,
        tenant_id=ctx.tenant_id,
        session_id=session_id,
    )

    if evaluation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation not found for this session.",
        )

    return evaluation
