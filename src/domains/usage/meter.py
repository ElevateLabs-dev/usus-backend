"""
Records what each training session costs.

Code that calls the AI for a session wraps the call in usage_scope(...); the
LLM providers then report each request's tokens with record_llm(), which is
saved in the background so it never slows a reply down. Voice calls are
recorded when their transcript is saved (record_voice_call).
"""

import asyncio
import logging
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterator

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import AsyncSessionLocal
from src.domains.usage.models import UsageRecord
from src.domains.usage.pricing import llm_cost

logger = logging.getLogger("usus.usage")

# Session factory used to save LLM usage (swapped out in tests).
_session_factory = AsyncSessionLocal


@dataclass(frozen=True)
class UsageScope:
    tenant_id: uuid.UUID
    session_id: uuid.UUID
    purpose: str


_scope: ContextVar[UsageScope | None] = ContextVar("usage_scope", default=None)
_pending: set[asyncio.Task] = set()


@contextmanager
def usage_scope(
    tenant_id: uuid.UUID, session_id: uuid.UUID, purpose: str
) -> Iterator[None]:
    """AI requests made inside this block are counted for the session."""
    token = _scope.set(UsageScope(tenant_id, session_id, purpose))
    try:
        yield
    finally:
        _scope.reset(token)


def record_llm(model: str, input_tokens: int, output_tokens: int) -> None:
    """Called by the LLM providers after each request. Outside a usage scope
    (health checks, scripts) nothing is recorded."""
    scope = _scope.get()
    if scope is None:
        return
    record = UsageRecord(
        tenant_id=scope.tenant_id,
        session_id=scope.session_id,
        kind="llm",
        purpose=scope.purpose,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=llm_cost(model, input_tokens, output_tokens),
    )
    try:
        task = asyncio.get_running_loop().create_task(_save(record))
    except RuntimeError:
        return
    _pending.add(task)
    task.add_done_callback(_pending.discard)


async def _save(record: UsageRecord) -> None:
    try:
        async with _session_factory() as db:
            db.add(record)
            await db.commit()
    except Exception:
        logger.exception("Could not save usage for session %s", record.session_id)


async def drain() -> None:
    """Wait until all recorded usage is saved (used by tests)."""
    while _pending:
        await asyncio.gather(*list(_pending), return_exceptions=True)


def _seconds(call: dict[str, Any]) -> int:
    try:
        started = datetime.fromisoformat(str(call["startedAt"]).replace("Z", "+00:00"))
        ended = datetime.fromisoformat(str(call["endedAt"]).replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return 0
    return max(0, round((ended - started).total_seconds()))


def _cost(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def record_voice_call(
    db: AsyncSession, tenant_id: uuid.UUID, session_id: uuid.UUID, call: dict[str, Any]
) -> None:
    """Add the Vapi call's length and cost (Vapi's own total: calling,
    transcription and voice) to the caller's transaction."""
    db.add(
        UsageRecord(
            tenant_id=tenant_id,
            session_id=session_id,
            kind="voice",
            purpose="voice_call",
            model="vapi",
            seconds=_seconds(call),
            cost_usd=_cost(call.get("cost")),
        )
    )
