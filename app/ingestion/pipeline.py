import hashlib
import asyncio
import logging
from pathlib import Path

from openai import AsyncOpenAI
from psycopg.connection_async import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from app.ingestion.chunker import chunk_text, extract_text_from_file, iter_files
from app.ingestion.embedder import embed_chunks
from app.ingestion.models import EmbeddedChunk

logger = logging.getLogger(__name__)


async def ingest_documents(
    docs_dir: str, client: AsyncOpenAI, pool: AsyncConnectionPool
):
    """Ingest documents from the specified directory, chunk them, and embed the chunks."""
    logger.info("Starting ingestion of documents from %s", docs_dir)
    for file_path in iter_files(Path(docs_dir)):
        await ingest_file(file_path, client, pool)
    logger.info("Completed ingestion of documents from %s", docs_dir)


async def ingest_file(file_path: Path, client: AsyncOpenAI, pool: AsyncConnectionPool) -> bool:
    """Prepare embeddings before atomically replacing a file's indexed version."""
    logger.debug("Processing file: %s", file_path)
    text = await asyncio.to_thread(extract_text_from_file, file_path)
    if text is None:
        raise ValueError(f"Could not extract text from {file_path}")
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if await check_if_ingested(pool, file_path, content_hash):
        return False
    embedded = [chunk async for chunk in embed_chunks(chunk_text(file_path, text), client)]
    async with pool.connection() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM documents WHERE source_file = %s", (file_path.as_posix(),))
            for chunk in embedded:
                await save_embedded_chunk(conn, chunk)
            await mark_as_ingested(conn, file_path, content_hash, len(embedded))
    logger.info("Ingested file: %s chunks=%d", file_path, len(embedded))
    return True


async def save_embedded_chunk(conn: AsyncConnection, embedded_chunk: EmbeddedChunk):
    cursor = conn.cursor()
    logger.debug("Saving embedded chunk: %s - %s", embedded_chunk.source, embedded_chunk.position)
    await cursor.execute(
        """
            INSERT INTO documents (source_file, chunk_index, content, embedding)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (source_file, chunk_index) DO UPDATE
            SET content = EXCLUDED.content, 
                embedding = EXCLUDED.embedding
        """,
        (
            embedded_chunk.source.as_posix(),
            embedded_chunk.position,
            embedded_chunk.text,
            embedded_chunk.embedding,
        ),
    )


async def check_if_ingested(
    pool: AsyncConnectionPool, file_path: Path, content_hash: str
) -> bool:
    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute(
            "SELECT 1 from ingested_files WHERE source_file = %s AND content_hash = %s",
            (file_path.as_posix(), content_hash),
        )
        row = await cursor.fetchone()
        return row is not None


async def mark_as_ingested(
    conn: AsyncConnection, file_path: Path, content_hash: str, chunk_count: int = 0
):
    cursor = conn.cursor()
    await cursor.execute(
        """
            INSERT INTO ingested_files (source_file, content_hash, chunk_count) 
            VALUES (%s, %s, %s)
            ON CONFLICT (source_file) DO UPDATE 
            SET content_hash = EXCLUDED.content_hash, 
                chunk_count = EXCLUDED.chunk_count, 
                updated_at = NOW()
            """,
        (file_path.as_posix(), content_hash, chunk_count),
    )

async def remove_ingested_documents(pool: AsyncConnectionPool, file_path: Path):
    """Remove ingested documents and their embeddings for a given file."""
    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute(
            "DELETE FROM documents WHERE source_file = %s", (file_path.as_posix(),)
        )
        await cursor.execute(
            "DELETE FROM ingested_files WHERE source_file = %s", (file_path.as_posix(),)
        )
        await conn.commit()
