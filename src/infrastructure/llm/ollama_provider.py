from typing import Any, Dict, List

from ollama import AsyncClient

from src.core.config import settings
from src.infrastructure.llm.base import LLMProvider


class OllamaProvider(LLMProvider):
    """
    Ollama implementation of the LLMProvider.

    Connects to the Ollama server running in Docker
    and generates responses using the configured model.
    """

    def __init__(self, model: str | None = None):
        self.model = model or settings.OLLAMA_MODEL

        self.client = AsyncClient(
            host=settings.OLLAMA_HOST,
        )

    async def generate_response(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        temperature: float = 0.5,
        max_tokens: int = 180,
    ) -> str:
        """
        Generate a response using Ollama.
        """

        formatted_messages: List[Dict[str, str]] = []

        # Add system instructions.
        if system_prompt.strip():
            formatted_messages.append(
                {
                    "role": "system",
                    "content": system_prompt,
                }
            )

        # Convert internal message format to Ollama format.
        for msg in messages:
            role = msg.get("role")

            # Support the internal "model" role if it exists.
            if role == "model":
                role = "assistant"

            if role not in {"user", "assistant", "system"}:
                continue

            formatted_messages.append(
                {
                    "role": role,
                    "content": str(msg.get("content", "")),
                }
            )

        response = await self.client.chat(
            model=self.model,
            messages=formatted_messages,
            stream=False,
            options={
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        )

        return response.message.content.strip();