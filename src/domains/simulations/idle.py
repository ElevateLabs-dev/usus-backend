"""
Ends sessions the trainee left without pressing "end" (closed the tab, lost
connection). Runs every few minutes inside the API.

A text session ends after IDLE_SESSION_MINUTES without a message. A voice
session waits at least the longest call Vapi allows, then its call (if any)
is fetched from Vapi so the transcript and cost are kept. Sessions where the
trainee said something are evaluated as usual.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.config import settings
from src.core.database import AsyncSessionLocal
from src.domains.evaluations.runner import run_evaluation
from src.domains.simulations.models import Message, MessageRole, Session, SessionStatus
from src.domains.simulations.voice import save_voice_transcript
from src.infrastructure.llm.base import LLMProvider
from src.infrastructure.voice.vapi import VapiClient

logger = logging.getLogger("usus.idle")

SWEEP_SECONDS = 300


def _limits() -> tuple[timedelta, timedelta]:
    text = timedelta(minutes=settings.IDLE_SESSION_MINUTES)
    voice = max(text, timedelta(seconds=settings.VAPI_MAX_CALL_SECONDS + 300))
    return text, voice


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _parse(value) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


async def _save_call(db: AsyncSession, session: Session, vapi: VapiClient):
    """Keep the transcript and cost of the call the trainee left; returns
    when it ended, if known."""
    if not vapi.configured or not session.voice_assistant_id:
        return None
    try:
        call = await vapi.latest_call(session.voice_assistant_id)
        if call is None:
            await vapi.delete_assistant(session.voice_assistant_id)
            return None
        await save_voice_transcript(db, session, call["id"], vapi)
        return _parse(call.get("endedAt"))
    except Exception:
        logger.warning("Could not fetch the call of session %s", session.id)
        return None


async def end_idle_sessions(
    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
    vapi: VapiClient | None = None,
    llm_provider: LLMProvider | None = None,
    now: datetime | None = None,
) -> list[uuid.UUID]:
    """End the sessions idle for too long; returns their ids."""
    now = now or datetime.now(timezone.utc)
    text_limit, voice_limit = _limits()
    vapi = vapi or VapiClient()

    last_message = (
        select(Message.session_id, func.max(Message.created_at).label("at"))
        .where(Message.role != MessageRole.SYSTEM)
        .group_by(Message.session_id)
        .subquery()
    )

    ended: list[tuple[uuid.UUID, uuid.UUID, bool]] = []
    async with session_factory() as db:
        rows = await db.execute(
            select(Session, last_message.c.at)
            .outerjoin(last_message, last_message.c.session_id == Session.id)
            .where(Session.status == SessionStatus.IN_PROGRESS)
        )
        for session, last_at in rows.all():
            last_active = max(
                _utc(t) for t in (session.created_at, session.updated_at, last_at) if t
            )
            voice = bool(session.voice_assistant_id)
            if now - last_active < (voice_limit if voice else text_limit):
                continue

            # Claim it first, so a trainee ending it at the same time (or
            # another worker) does not end it twice.
            claimed = await db.execute(
                update(Session)
                .where(
                    Session.id == session.id,
                    Session.status == SessionStatus.IN_PROGRESS,
                )
                .values(status=SessionStatus.COMPLETED, ended_at=last_active)
                .execution_options(synchronize_session=False)
            )
            await db.commit()
            if claimed.rowcount != 1:
                continue

            if voice and not session.voice_call_id:
                call_ended = await _save_call(db, session, vapi)
                if call_ended:
                    session.ended_at = call_ended
                    await db.commit()

            spoke = bool(
                await db.scalar(
                    select(Message.id)
                    .where(
                        Message.session_id == session.id,
                        Message.role == MessageRole.USER,
                    )
                    .limit(1)
                )
            )
            ended.append((session.id, session.tenant_id, spoke))
            logger.info("Ended idle session %s", session.id)

    for session_id, tenant_id, spoke in ended:
        if spoke:
            await run_evaluation(session_id, tenant_id, session_factory, llm_provider)
    return [session_id for session_id, _, _ in ended]


async def run_forever() -> None:
    """The sweep loop started with the API."""
    while True:
        try:
            await end_idle_sessions()
        except Exception:
            logger.exception("Ending idle sessions failed")
        await asyncio.sleep(SWEEP_SECONDS)
