from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import AsyncSessionLocal, get_db
from src.core.dependencies import AuthContext, UserRole, require_roles
from src.domains.evaluations.runner import run_evaluation
from src.domains.simulations.crud import session as session_repo
from src.domains.simulations.models import SessionStatus
from src.infrastructure.llm.base import LLMProvider

# Used by the background evaluation (swapped out in tests). None = the LLM
# provider selected by settings.
_session_factory = AsyncSessionLocal
_llm_provider: LLMProvider | None = None

router = APIRouter(
    prefix="/api/v1/evaluations",
    tags=["Evaluations"],
)


@router.post(
    "/{session_id}/generate",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Re-run a session's evaluation (Manager+)",
    description=(
        "**Company admin / manager only.** Starts the AI evaluation of a "
        "completed session in your organization in the background, e.g. if it "
        "failed earlier. An already-evaluated session is left unchanged."
    ),
    responses={
        401: {"description": "Missing or invalid token"},
        403: {"description": "Not a manager or admin"},
        404: {"description": "Session not found in your organization"},
        409: {"description": "Session has not been completed yet"},
    },
)
async def trigger_evaluation(
    session_id: UUID,
    ctx: Annotated[
        AuthContext,
        Depends(
            require_roles(
                UserRole.MANAGER, UserRole.COMPANY_ADMIN, UserRole.PLATFORM_ADMIN
            )
        ),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant context required",
        )
    session = await session_repo.get(db=db, id=session_id, tenant_id=ctx.tenant_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )
    if session.status == SessionStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Session has not been completed yet",
        )

    background_tasks.add_task(
        run_evaluation, session_id, ctx.tenant_id, _session_factory, _llm_provider
    )
    return {"session_id": str(session_id), "status": "processing"}
