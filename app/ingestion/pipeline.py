import hashlib
from pathlib import Path

from psycopg.connection_async import AsyncConnection

from app.db import get_pg_pool
from app.ingestion.chunker import chunk_text, extract_text_from_file, iter_files
from app.ingestion.embedder import embed_chunks
from app.ingestion.models import EmbeddedChunk


async def ingest_documents(docs_dir: str):
    """Ingest documents from the specified directory, chunk them, and embed the chunks."""

    for file_path in iter_files(Path(docs_dir)):
        text = extract_text_from_file(file_path)
        if text is not None:
            chunk_count = 0
            content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            async with get_pg_pool().connection() as conn:
                if await check_if_ingested(conn, file_path, content_hash):
                    continue  # Skip already ingested files
                async for embedded_chunk in embed_chunks(chunk_text(file_path, text)):
                    await save_embedded_chunk(conn, embedded_chunk)
                    chunk_count += 1
                await mark_as_ingested(conn, file_path, content_hash, chunk_count)
                await conn.commit()


async def save_embedded_chunk(conn: AsyncConnection, embedded_chunk: EmbeddedChunk):
    cursor = conn.cursor()
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
    conn: AsyncConnection, file_path: Path, content_hash: str
) -> bool:
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
