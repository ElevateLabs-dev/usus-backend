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
        response_format: str | Dict[str, Any] | None = None,
    ) -> str:
        """
        Generate a response using Ollama.

        response_format:
            Optional Ollama response format.

            Use "json" when the caller requires a valid
            JSON response.
        """

        formatted_messages: List[
            Dict[str, str]
        ] = []

        # ------------------------------------------------------------
        # Add system instructions
        # ------------------------------------------------------------

        if system_prompt.strip():
            formatted_messages.append(
                {
                    "role": "system",
                    "content": system_prompt,
                }
            )

        # ------------------------------------------------------------
        # Convert internal message format to Ollama format
        # ------------------------------------------------------------

        for msg in messages:
            role = msg.get("role")

            # Support the internal "model" role.
            if role == "model":
                role = "assistant"

            if role not in {
                "user",
                "assistant",
                "system",
            }:
                continue

            formatted_messages.append(
                {
                    "role": role,
                    "content": str(
                        msg.get("content", "")
                    ),
                }
            )

        # ------------------------------------------------------------
        # Build Ollama request
        # ------------------------------------------------------------

        request_options: Dict[str, Any] = {
            "temperature": temperature,
            "num_predict": max_tokens,
        }

        response_kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": formatted_messages,
            "stream": False,
            "options": request_options,
        }

        # ------------------------------------------------------------
        # Enable native JSON output when requested
        # ------------------------------------------------------------

        if response_format is not None:
            response_kwargs["format"] = response_format

        response = await self.client.chat(
            **response_kwargs,
        )

        return response.message.content.strip()