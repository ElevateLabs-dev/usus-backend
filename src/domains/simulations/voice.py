"""
Voice role-play with Vapi.

1. start_voice: creates a Vapi assistant for the session from the same customer
   prompt as text role-play. Only its id goes to the browser, so the hidden
   scenario details never do.
2. The browser runs the call with the Vapi Web SDK.
3. finish_voice: once the call has ended, copies Vapi's transcript into the
   session's messages and ends the session, so it is evaluated like a text
   session.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.simulations.crud import message as message_repo
from src.domains.simulations.models import Message, MessageRole, Session, SessionStatus
from src.infrastructure.voice.vapi import VapiClient

logger = logging.getLogger("usus.voice")

VOICE_INSTRUCTIONS = """

This conversation is a live phone call, spoken out loud.
- Reply in one to three short sentences, the way people talk on the phone.
- Never use lists, markdown, emojis or stage directions.
- Do not end the call yourself; keep going until the trainee hangs up."""

# Vapi can take a few seconds after hang-up to finish the transcript.
_CALL_POLL_ATTEMPTS = 8
_CALL_POLL_SECONDS = 1.5

_ROLES = {
    "user": MessageRole.USER,
    "bot": MessageRole.MODEL,
    "assistant": MessageRole.MODEL,
}


class VoiceError(Exception):
    """The voice call cannot be started or finished."""


def assistant_config(session: Session, scenario_name: str, prompt: str) -> dict:
    return {
        "name": f"Usus {scenario_name}"[:40],
        # The trainee answers the call, like in text role-play.
        "firstMessageMode": "assistant-waits-for-user",
        "model": {
            "provider": "openai",
            "model": settings.VAPI_MODEL,
            "messages": [{"role": "system", "content": prompt + VOICE_INSTRUCTIONS}],
        },
        "voice": {
            "provider": settings.VAPI_VOICE_PROVIDER,
            "voiceId": settings.VAPI_VOICE_ID,
        },
        "transcriber": {"provider": "deepgram", "model": "nova-3", "language": "en"},
        "maxDurationSeconds": settings.VAPI_MAX_CALL_SECONDS,
        "metadata": {
            "session_id": str(session.id),
            "tenant_id": str(session.tenant_id),
        },
    }


async def start_voice(
    db: AsyncSession, session: Session, scenario_name: str, vapi: VapiClient
) -> str:
    """Create (or reuse) the session's Vapi assistant and return its id."""
    if session.status != SessionStatus.IN_PROGRESS:
        raise VoiceError("The session is no longer active")
    if session.voice_assistant_id:
        return session.voice_assistant_id

    messages = await message_repo.get_by_session(
        db=db, tenant_id=session.tenant_id, session_id=session.id
    )
    prompt = next((m.content for m in messages if m.role == MessageRole.SYSTEM), "")

    session.voice_assistant_id = await vapi.create_assistant(
        assistant_config(session, scenario_name, prompt)
    )
    await db.commit()
    return session.voice_assistant_id


def _transcript(call: dict[str, Any]) -> list[tuple[MessageRole, str]]:
    raw = call.get("messages") or (call.get("artifact") or {}).get("messages") or []
    lines = []
    for item in raw:
        role = _ROLES.get(item.get("role", ""))
        text = (item.get("message") or "").strip()
        if role and text:
            lines.append((role, text))
    return lines


async def _ended_call(vapi: VapiClient, call_id: str) -> dict[str, Any]:
    call = await vapi.get_call(call_id)
    for _ in range(_CALL_POLL_ATTEMPTS):
        if call.get("status") == "ended":
            break
        await asyncio.sleep(_CALL_POLL_SECONDS)
        call = await vapi.get_call(call_id)
    return call


async def save_voice_transcript(
    db: AsyncSession, session: Session, call_id: str, vapi: VapiClient
) -> None:
    """Copy the call's transcript into the session. Only for an in-progress
    session whose assistant made the call."""
    if not session.voice_assistant_id:
        raise VoiceError("This session has no voice call")

    call = await _ended_call(vapi, call_id)
    if call.get("assistantId") != session.voice_assistant_id:
        raise VoiceError("This call does not belong to the session")

    # Messages are listed by created_at; one transaction would give them all
    # the same time, so space them a millisecond apart to keep their order.
    started = datetime.now(timezone.utc)
    db.add_all(
        Message(
            tenant_id=session.tenant_id,
            session_id=session.id,
            role=role,
            content=text,
            created_at=started + timedelta(milliseconds=index),
        )
        for index, (role, text) in enumerate(_transcript(call))
    )
    session.voice_call_id = call_id
    await db.commit()

    # The assistant was made for this one session.
    try:
        await vapi.delete_assistant(session.voice_assistant_id)
    except Exception:
        logger.warning("Could not delete Vapi assistant %s", session.voice_assistant_id)
