from typing import Any, Dict, List

from openai import AsyncOpenAI

from src.core.config import settings
from src.infrastructure.llm.base import LLMProvider

# Reasoning models only accept the default temperature and reject custom values.
_FIXED_TEMPERATURE_PREFIXES = ("gpt-5", "o1", "o3", "o4")


class OpenAIProvider(LLMProvider):
    """
    OpenAI implementation of the LLMProvider using the official SDK
    (Chat Completions API).
    """

    def __init__(self, model: str | None = None):
        self.model = model or settings.OPENAI_MODEL
        self.client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )

    async def generate_response(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> str:
        """
        Generate a response using OpenAI chat models.
        """
        formatted_messages: List[Dict[str, str]] = []

        if system_prompt.strip():
            formatted_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            role = msg.get("role")

            # Our internal enum uses "model" for AI turns; OpenAI calls it "assistant".
            if role == "model":
                role = "assistant"

            if role not in {"user", "assistant", "system"}:
                continue

            formatted_messages.append(
                {"role": role, "content": str(msg.get("content", ""))}
            )

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": formatted_messages,
            "max_completion_tokens": max_tokens,
        }

        if not self.model.startswith(_FIXED_TEMPERATURE_PREFIXES):
            kwargs["temperature"] = temperature

        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = await self.client.chat.completions.create(**kwargs)

        return (response.choices[0].message.content or "").strip()
