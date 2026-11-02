"""
The AI customer's replies, shared by text and voice role-play.

Every reply is checked before anyone hears or reads it: a reply that sounds
like the agent, an AI or the trainer is generated again with a stricter
reminder, and if that fails too, a fixed in-character line is used. So the
customer never switches roles, whatever the trainee says.
"""

import logging
import re
from typing import Any, AsyncIterator

from src.domains.scenarios.models import Scenario
from src.domains.scenarios.prompts import (
    STAY_IN_ROLE_REPLY,
    breaks_role,
    customer_reminder,
    split_mood,
    strict_reminder,
)
from src.infrastructure.llm.base import LLMProvider

logger = logging.getLogger("usus.customer")


async def customer_reply(
    llm: LLMProvider,
    scenario: Scenario | None,
    system_prompt: str,
    history: list[dict[str, Any]],
    max_tokens: int = 300,
) -> tuple[str | None, str]:
    """
    The customer's next reply to the conversation in history (user = agent,
    model/assistant = customer). Returns (mood, text); the mood tag is never
    part of the text.
    """
    messages = [dict(message) for message in history]
    reminders = [
        customer_reminder(scenario) if scenario else "",
        strict_reminder(scenario) if scenario else "",
    ]
    last_content = messages[-1]["content"] if messages else ""

    for attempt, reminder in enumerate(reminders):
        if messages and reminder:
            messages[-1]["content"] = f"{last_content}\n\n{reminder}"
        raw = await llm.generate_response(
            system_prompt=system_prompt,
            messages=messages,
            temperature=0.7 if attempt == 0 else 0.4,
            max_tokens=max_tokens,
        )
        mood, text = split_mood(raw)
        if text and not breaks_role(text):
            return mood, text
        logger.warning("Customer reply left its role (attempt %d)", attempt + 1)

    return None, STAY_IN_ROLE_REPLY


# A sentence is complete once its end mark is followed by a space.
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


async def stream_customer_reply(
    llm: LLMProvider,
    scenario: Scenario | None,
    system_prompt: str,
    history: list[dict[str, Any]],
    max_tokens: int = 200,
) -> AsyncIterator[str]:
    """
    The customer's reply, sentence by sentence as it is generated, so a voice
    can start speaking early. Each sentence is checked before it is yielded:
    if the first one leaves the role, the checked reply from customer_reply is
    used instead; if a later one does, the reply stops there.
    """
    messages = [dict(message) for message in history]
    if messages and scenario is not None:
        messages[-1]["content"] += f"\n\n{customer_reminder(scenario)}"

    buffer = ""
    spoken = ""
    started = False  # past the leading [mood: ...] tag
    stopped = False  # a sentence left the role

    def checked(sentence: str) -> str | None:
        """The sentence without mood tags, or None if it leaves the role."""
        _mood, text = split_mood(sentence)
        if text and breaks_role(f"{spoken} {text}"):
            logger.warning("Streamed customer reply left its role")
            return None
        return text

    async for piece in llm.stream_response(
        system_prompt=system_prompt,
        messages=messages,
        temperature=0.7,
        max_tokens=max_tokens,
    ):
        buffer += piece
        if not started:
            head = buffer.lstrip()
            if head.startswith("[") and "]" not in head and len(head) < 40:
                continue  # wait for the whole mood tag
            started = True

        while match := _SENTENCE_END.search(buffer):
            sentence, buffer = buffer[: match.start()], buffer[match.end() :]
            text = checked(sentence)
            if text is None:
                stopped = True
                break
            if text:
                yield f"{text} "
                spoken += f" {text}"
        if stopped:
            break

    if not stopped:
        text = checked(buffer)
        if text:
            yield text
            spoken += f" {text}"

    if not spoken:
        _mood, text = await customer_reply(llm, scenario, system_prompt, history)
        yield text
