"""
The AI customer's replies, shared by text and voice role-play.

Every reply is checked before anyone hears or reads it: a reply that sounds
like the agent, an AI or the trainer is generated again with a stricter
reminder, and if that fails too, a fixed in-character line is used. So the
customer never switches roles, whatever the trainee says.
"""

import logging
from typing import Any

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
