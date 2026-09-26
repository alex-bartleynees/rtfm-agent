import itertools
import logging
from time import perf_counter
from typing import AsyncGenerator, Iterable

from openai import AsyncOpenAI

from app.config import settings
from app.ingestion.models import Chunk, EmbeddedChunk

logger = logging.getLogger(__name__)


async def embed_chunks(
    chunks: Iterable[Chunk], client: AsyncOpenAI
) -> AsyncGenerator[EmbeddedChunk, None]:
    """Embed a list of chunks using the embedding model."""
    for batch in itertools.batched(chunks, 32):
        logger.info(
            "Starting embedding request: model=%s chunks=%d source=%s",
            settings.embedding_model, len(batch), batch[0].source,
        )
        started = perf_counter()
        try:
            embeddings = await client.embeddings.create(
                model=settings.embedding_model, input=[chunk.text for chunk in batch]
            )
        except Exception:
            logger.exception(
                "Embedding request failed: model=%s chunks=%d source=%s elapsed=%.2fs",
                settings.embedding_model, len(batch), batch[0].source,
                perf_counter() - started,
            )
            raise
        logger.info(
            "Embedding request completed: model=%s embeddings=%d source=%s elapsed=%.2fs",
            settings.embedding_model, len(embeddings.data), batch[0].source,
            perf_counter() - started,
        )
        for data_item in embeddings.data:
            chunk = batch[data_item.index]
            yield EmbeddedChunk(
                text=chunk.text,
                source=chunk.source,
                position=chunk.position,
                embedding=data_item.embedding,
            )
