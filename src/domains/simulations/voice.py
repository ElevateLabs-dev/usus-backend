"""
Voice role-play with Vapi.

1. start_voice: creates a Vapi assistant for the session. Only its id goes to
   the browser, so the hidden scenario details never do.
2. The browser runs the call with the Vapi Web SDK. For every turn, Vapi asks
   our voice/llm endpoint for the customer's reply, which uses the same
   customer prompt and role check as text role-play.
3. finish_voice: once the call has ended, copies Vapi's transcript into the
   session's messages and ends the session, so it is evaluated like a text
   session.
"""

import asyncio
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.scenarios.models import Scenario
from src.domains.scenarios.voices import scenario_mood, voice_config
from src.domains.simulations.models import Message, MessageRole, Session, SessionStatus
from src.infrastructure.voice.vapi import VapiClient

logger = logging.getLogger("usus.voice")

VOICE_INSTRUCTIONS = """

This conversation is a live phone call, spoken out loud.
- Reply in one to three short sentences, the way people talk on the phone.
- Start each reply with a short reaction of a few words ("Oh, okay.", "Right, \
so...", "Hmm.") before you say more, like a person thinking out loud.
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


# Vapi sends this header (set on the assistant) with every turn.
VOICE_TOKEN_HEADER = "x-usus-voice-token"


class VoiceError(Exception):
    """The voice call cannot be started or finished."""


def assistant_config(
    session: Session, scenario: Scenario, llm_url: str, token: str
) -> dict:
    """
    The Vapi assistant for a session. Vapi sends every turn to our own
    endpoint (llm_url), which writes the customer's reply with the role check,
    so the customer prompt never leaves our server.
    """
    return {
        "name": f"Usus {scenario.name}"[:40],
        # The trainee answers the call, like in text role-play.
        "firstMessageMode": "assistant-waits-for-user",
        "model": {
            "provider": "custom-llm",
            "url": llm_url,
            "model": settings.VAPI_MODEL,
            "headers": {VOICE_TOKEN_HEADER: token},
            "metadataSendMode": "off",
            "timeoutSeconds": 20,
        },
        "voice": voice_config(scenario.voice_id, scenario_mood(scenario)),
        "transcriber": {"provider": "deepgram", "model": "nova-3", "language": "en"},
        "maxDurationSeconds": settings.VAPI_MAX_CALL_SECONDS,
        "metadata": {
            "session_id": str(session.id),
            "tenant_id": str(session.tenant_id),
        },
    }


async def start_voice(
    db: AsyncSession,
    session: Session,
    scenario: Scenario,
    api_base_url: str,
    vapi: VapiClient,
) -> str:
    """Create (or reuse) the session's Vapi assistant and return its id."""
    if session.status != SessionStatus.IN_PROGRESS:
        raise VoiceError("The session is no longer active")
    if session.voice_assistant_id:
        return session.voice_assistant_id

    session.voice_token = secrets.token_urlsafe(32)
    llm_url = f"{api_base_url.rstrip('/')}/api/v1/simulations/{session.id}/voice/llm"
    session.voice_assistant_id = await vapi.create_assistant(
        assistant_config(session, scenario, llm_url, session.voice_token)
    )
    await db.commit()
    return session.voice_assistant_id


def valid_voice_token(session: Session, token: str | None) -> bool:
    """Whether a request to the session's voice endpoint comes from its call."""
    return bool(
        session.voice_token
        and token
        and hmac.compare_digest(session.voice_token, token)
    )


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
