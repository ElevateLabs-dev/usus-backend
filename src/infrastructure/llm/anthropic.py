import anthropic
from typing import Any, Dict, List

from anthropic.types import TextBlock
from src.infrastructure.llm.base import LLMProvider
from src.core.config import settings


class AnthropicProvider(LLMProvider):
    """
    Anthropic implementation of the LLMProvider using the official SDK.
    """

    def __init__(self, model: str | None = None):
        self.model = model or settings.ANTHROPIC_MODEL
        self.client = anthropic.AsyncAnthropic(
            api_key=settings.ANTHROPIC_API_KEY,
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
        Generate a response using Anthropic's Claude models.

        json_mode is accepted for interface compatibility; JSON output is
        enforced through the system prompt.
        """
        # Ensure messages conform to what Anthropic expects (user/assistant roles).
        # We might need to map 'model' to 'assistant' if our internal enum uses 'model'.
        formatted_messages = []
        for msg in messages:
            role = msg.get("role")
            if role == "model":
                role = "assistant"

            formatted_messages.append({"role": role, "content": msg.get("content", "")})

        response = await self.client.messages.create(
            model=self.model,
            system=system_prompt,
            messages=formatted_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        text_parts: List[str] = [
            block.text for block in response.content if isinstance(block, TextBlock)
        ]

        return "\n".join(text_parts).strip()
