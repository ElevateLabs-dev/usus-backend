from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import AsyncSessionLocal, get_db
from src.core.dependencies import AuthContext, get_auth_context
from src.domains.evaluations.crud import (
    evaluation_result as eval_result_repo,
)
from src.domains.evaluations.runner import run_evaluation
from src.domains.evaluations.schemas import (
    EvaluationResultDetailResponse,
)
from src.domains.scenarios.crud import scenario as scenario_repo
from src.domains.simulations import history
from src.domains.simulations.crud import (
    message as message_repo,
)
from src.domains.simulations.crud import (
    session as session_repo,
)
from src.domains.simulations.models import MessageRole, Session, SessionStatus
from src.domains.simulations.schemas import (
    HistoryPage,
    SendMessageRequest,
    SendMessageResponse,
    SessionDetail,
    SessionResponse,
    StartSessionRequest,
)
from src.domains.simulations.service import SimulationService
from src.infrastructure.llm.factory import get_llm_provider

# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

_llm = get_llm_provider()

_simulation_service = SimulationService(
    session_repo=session_repo,
    message_repo=message_repo,
    scenario_repo=scenario_repo,
    llm_provider=_llm,
)


# Session factory used by the background evaluation (swapped out in tests).
_session_factory = AsyncSessionLocal


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(
    prefix="/api/v1/simulations",
    tags=["Simulations"],
)

_AUTH_ERRORS: dict[int | str, dict] = {
    401: {"description": "Missing/invalid token, or no organization in the token"},
    403: {"description": "Password change required"},
}


def _tenant_of(ctx: AuthContext) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant context required",
        )
    return ctx.tenant_id


async def _owned_session(
    db: AsyncSession, ctx: AuthContext, session_id: UUID
) -> Session:
    """The session, if it exists in the caller's organization AND is theirs."""
    session = await session_repo.get(db=db, id=session_id, tenant_id=_tenant_of(ctx))
    if session is None or session.user_id != ctx.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    return session


@router.get("/health", include_in_schema=False)
async def simulation_health_check():
    return {
        "status": "ok",
        "domain": "simulations",
    }


@router.post(
    "/start",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a role-play session",
    description=(
        "Opens a session for a scenario. The AI customer is configured from the "
        "scenario. Then send the trainee's messages with "
        "`POST /simulations/{session_id}/message`."
    ),
    responses={**_AUTH_ERRORS, 404: {"description": "Scenario not found"}},
)
async def start_simulation(
    body: StartSessionRequest,
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        session = await _simulation_service.start_session(
            db=db,
            user_id=ctx.user_id,
            tenant_id=_tenant_of(ctx),
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
    summary="Send a message to the AI customer",
    description=(
        "Saves the trainee's message and returns it together with the AI "
        "customer's reply (usually 2-6 seconds)."
    ),
    responses={
        **_AUTH_ERRORS,
        400: {"description": "The session is no longer active"},
        404: {"description": "Session not found"},
    },
)
async def send_message(
    session_id: UUID,
    body: SendMessageRequest,
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    session = await _owned_session(db, ctx, session_id)
    tenant_id = session.tenant_id

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
        message for message in all_messages if message.role != MessageRole.SYSTEM
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
    summary="End the session (evaluation runs in the background)",
    description=(
        "Marks the session `completed` and returns immediately. The AI "
        "evaluation — 7 dimensions (Accuracy, Empathy, Clarity, Policy, "
        "Resolution, De-escalation, Efficiency; 0-100 each) plus strengths, "
        "improvements, missed opportunities and recommendations — is generated "
        "in the background, usually within 10-30 seconds.\n\n"
        "Poll `GET /simulations/{session_id}/evaluation` until it returns 200; "
        "the session's status then becomes `evaluated`.\n\n"
        "Safe to call again: for a `completed` session it queues the evaluation "
        "again (retrying one that failed); an `evaluated` session is unchanged."
    ),
    responses={**_AUTH_ERRORS, 404: {"description": "Session not found"}},
)
async def end_simulation(
    session_id: UUID,
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    session = await _owned_session(db, ctx, session_id)

    try:
        completed_session = await _simulation_service.end_session(
            db=db,
            tenant_id=session.tenant_id,
            session_id=session_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    # Evaluation runs in the background after the response is sent.
    # The API returns immediately instead of waiting for the LLM.
    if completed_session.status == SessionStatus.COMPLETED:
        background_tasks.add_task(
            run_evaluation,
            session_id,
            session.tenant_id,
            _session_factory,
            _simulation_service.llm_provider,
        )

    return completed_session


@router.get(
    "/{session_id}/evaluation",
    response_model=EvaluationResultDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a session's evaluation",
    description=(
        "Returns 404 with `Evaluation is still being generated.` while the "
        "background evaluation is running — poll every few seconds."
    ),
    responses={
        **_AUTH_ERRORS,
        404: {"description": "Session not found, or evaluation not ready yet"},
    },
)
async def get_evaluation(
    session_id: UUID,
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    session = await _owned_session(db, ctx, session_id)

    evaluation = await eval_result_repo.get_by_session_with_details(
        db=db,
        tenant_id=session.tenant_id,
        session_id=session_id,
    )

    if evaluation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Evaluation is still being generated."
                if session.status == SessionStatus.COMPLETED
                else "Evaluation not found for this session."
            ),
        )

    return evaluation


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=HistoryPage,
    summary="Your training history",
    description=(
        "Your sessions, newest first, with scenario, status, duration and overall "
        "score. Paginate with `limit`/`offset`; `total` is the number of matching "
        "sessions."
    ),
    responses=_AUTH_ERRORS,
)
async def list_sessions(
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    scenario_id: Annotated[
        UUID | None, Query(description="Only sessions for this scenario")
    ] = None,
    session_status: Annotated[
        SessionStatus | None,
        Query(alias="status", description="Only sessions with this status"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return await history.list_history(
        db,
        _tenant_of(ctx),
        ctx.user_id,
        scenario_id=scenario_id,
        status=session_status,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{session_id}",
    response_model=SessionDetail,
    summary="Get one session with transcript and evaluation",
    description=(
        "A past (or open) session: the full conversation in order and its "
        "evaluation (`null` until the session is evaluated)."
    ),
    responses={**_AUTH_ERRORS, 404: {"description": "Session not found"}},
)
async def get_session(
    session_id: UUID,
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    detail = await history.get_session_detail(
        db, _tenant_of(ctx), ctx.user_id, session_id
    )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )
    return detail
