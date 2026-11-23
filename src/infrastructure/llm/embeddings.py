"""Text embeddings (OpenAI) for searching the knowledge base."""

from openai import AsyncOpenAI

from src.core.config import settings

EMBEDDING_DIMENSIONS = 1536  # text-embedding-3-small
_BATCH = 100


class EmbeddingsUnavailable(Exception):
    pass


class Embedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not settings.OPENAI_API_KEY:
            raise EmbeddingsUnavailable("OPENAI_API_KEY is not set")
        client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY, timeout=settings.LLM_TIMEOUT_SECONDS
        )
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _BATCH):
            response = await client.embeddings.create(
                model=settings.EMBEDDING_MODEL,
                input=texts[start : start + _BATCH],
                dimensions=EMBEDDING_DIMENSIONS,
            )
            vectors.extend(item.embedding for item in response.data)
        return vectors
