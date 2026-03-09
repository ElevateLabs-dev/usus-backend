import anthropic
from typing import Any, Dict, List

from anthropic.types import TextBlock
from src.infrastructure.llm.base import LLMProvider
from src.core.config import settings


class AnthropicProvider(LLMProvider):
    """
    Anthropic implementation of the LLMProvider using the official SDK.
    """

    def __init__(self, model: str = "claude-3-5-sonnet-20241022"):
        self.model = model
        # The AsyncAnthropic client will automatically use ANTHROPIC_API_KEY from environment
        self.client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    async def generate_response(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """
        Generate a response using Anthropic's Claude models.
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
