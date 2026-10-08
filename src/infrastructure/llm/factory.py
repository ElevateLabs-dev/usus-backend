from src.core.config import settings
from src.infrastructure.llm.base import LLMProvider


def get_llm_provider(name: str | None = None) -> LLMProvider:
    """
    Build the LLM provider selected by settings.LLM_PROVIDER
    ("openai" or "anthropic").
    """
    provider = (name or settings.LLM_PROVIDER).strip().lower()

    # Imports are local so an unused provider's SDK is never loaded.
    if provider == "openai":
        from src.infrastructure.llm.openai_provider import OpenAIProvider

        return OpenAIProvider()

    if provider == "anthropic":
        from src.infrastructure.llm.anthropic import AnthropicProvider

        return AnthropicProvider()

    raise ValueError(
        f"Unknown LLM_PROVIDER {provider!r}. Use 'openai' or 'anthropic'."
    )
