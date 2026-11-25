"""
Knowledge base: an organization's policies and documents (PDF / Word).

On upload the text is read, split into passages and embedded in the
background. search() finds the passages closest to a piece of text; it is used
to suggest scenarios and, when the organization turns it on, by the evaluator.
"""

import asyncio
import logging
import math
import uuid

import openai
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domains.knowledge.extract import ExtractionError, chunk_text, extract_text
from src.domains.knowledge.models import Document, DocumentChunk, DocumentStatus
from src.infrastructure.llm.embeddings import Embedder, EmbeddingsUnavailable

logger = logging.getLogger("usus.knowledge")

MAX_CHUNKS = 2000  # about 2 million characters per document

# Swapped out in tests
embedder = Embedder()


async def process_document(
    document_id: uuid.UUID,
    data: bytes,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Background task: read, split and embed an uploaded document."""
    async with session_factory() as db:
        document = await db.get(Document, document_id)
        if document is None:
            return
        try:
            text = await asyncio.to_thread(extract_text, data, document.file_type)
            chunks = chunk_text(text)
            if len(chunks) > MAX_CHUNKS:
                raise ExtractionError("This document is too long")
            vectors = await embedder.embed(chunks)
        except ExtractionError as exc:
            await _fail(db, document, str(exc))
            return
        except EmbeddingsUnavailable:
            await _fail(db, document, "Document processing is not available yet")
            return
        except (openai.APIStatusError, openai.APIConnectionError):
            logger.exception("Embedding document %s failed", document_id)
            await _fail(
                db,
                document,
                "The AI service is not available right now. Retry in a few minutes.",
            )
            return
        except Exception:
            logger.exception("Processing document %s failed", document_id)
            await _fail(db, document, "Processing failed. Please retry.")
            return

        # Deleted while it was being processed
        still_there = await db.execute(
            select(Document.id).where(Document.id == document_id)
        )
        if still_there.first() is None:
            return
        db.add_all(
            DocumentChunk(
                tenant_id=document.tenant_id,
                document_id=document.id,
                position=index,
                content=chunk,
                embedding=vector,
            )
            for index, (chunk, vector) in enumerate(zip(chunks, vectors))
        )
        document.status = DocumentStatus.READY.value
        document.char_count = len(text)
        document.chunk_count = len(chunks)
        document.error = None
        await db.commit()


async def _fail(db: AsyncSession, document: Document, reason: str) -> None:
    document.status = DocumentStatus.FAILED.value
    document.error = reason
    await db.commit()


async def ready_count(db: AsyncSession, tenant_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count(Document.id)).where(
            Document.tenant_id == tenant_id,
            Document.status == DocumentStatus.READY.value,
        )
    )
    return result.scalar_one()


def _cosine_distance(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return 1 - dot / norm if norm else 1.0


async def search(
    db: AsyncSession, tenant_id: uuid.UUID, query: str, limit: int = 5
) -> list[str]:
    """The passages of the organization's documents closest to `query`."""
    if not query.strip() or not await ready_count(db, tenant_id):
        return []
    [vector] = await embedder.embed([query[:8000]])
    base = select(DocumentChunk.content, DocumentChunk.embedding).where(
        DocumentChunk.tenant_id == tenant_id
    )
    if db.get_bind().dialect.name == "postgresql":
        rows = await db.execute(
            base.order_by(DocumentChunk.embedding.cosine_distance(vector)).limit(limit)
        )
        return [content for content, _ in rows.all()]
    # SQLite (tests): rank in Python
    rows = (await db.execute(base)).all()
    rows.sort(key=lambda row: _cosine_distance(row[1], vector))
    return [content for content, _ in rows[:limit]]


async def sample_passages(
    db: AsyncSession, tenant_id: uuid.UUID, limit: int
) -> list[str]:
    """Up to `limit` passages, taken from every ready document in turn."""
    rows = await db.execute(
        select(DocumentChunk.document_id, DocumentChunk.content)
        .where(DocumentChunk.tenant_id == tenant_id)
        .order_by(DocumentChunk.document_id, DocumentChunk.position)
    )
    by_document: dict[uuid.UUID, list[str]] = {}
    for document_id, content in rows.all():
        by_document.setdefault(document_id, []).append(content)
    queues = list(by_document.values())
    picked: list[str] = []
    while queues and len(picked) < limit:
        for queue in queues:
            if queue and len(picked) < limit:
                picked.append(queue.pop(0))
        queues = [q for q in queues if q]
    return picked
