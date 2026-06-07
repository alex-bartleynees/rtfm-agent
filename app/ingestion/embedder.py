import itertools
from typing import AsyncGenerator, Iterable

from app.ai_client import get_ai_client
from app.config import settings
from app.ingestion.models import Chunk, EmbeddedChunk


async def embed_chunks(chunks: Iterable[Chunk]) -> AsyncGenerator[EmbeddedChunk, None]:
    """Embed a list of chunks using the embedding model."""
    client = get_ai_client()
    for batch in itertools.batched(chunks, 32):
        embeddings = await client.embeddings.create(
            model=settings.embedding_model, input=[chunk.text for chunk in batch]
        )
        for data_item in embeddings.data:
            chunk = batch[data_item.index]
            yield EmbeddedChunk(
                text=chunk.text,
                source=chunk.source,
                position=chunk.position,
                embedding=data_item.embedding,
            )
