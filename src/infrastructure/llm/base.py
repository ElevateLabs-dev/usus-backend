from typing import Any, Dict, List
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """
    Abstract Base Class for Large Language Model Providers.
    """

    @abstractmethod
    async def generate_response(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> str:
        """
        Generate a response from the LLM.

        Args:
            system_prompt: The overarching system instructions.
            messages: A list of message dictionaries. Expected format:
                      [{"role": "user" | "assistant", "content": "..."}]
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            json_mode: Ask the provider to return a valid JSON object, where supported.

        Returns:
            The string response from the model.
        """
        pass
