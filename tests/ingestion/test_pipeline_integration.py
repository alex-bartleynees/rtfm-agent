"""Integration tests for the ingestion pipeline against a real pgvector Postgres.

Only the embedding model is faked - everything else (schema, SQL, connection
pool, chunking, file discovery) is the real thing running against a container.
"""

from pathlib import Path

import pytest
from psycopg_pool import AsyncConnectionPool
from testcontainers.community.postgres import PostgresContainer

from app.config import settings
from app.ingestion.pipeline import ingest_documents, ingest_file

pytestmark = pytest.mark.integration

SCHEMA_FILE = Path(__file__).parents[2] / "scripts" / "postgres-schema.sql"


class FakeEmbeddings:
    """Stands in for `AsyncOpenAI.embeddings`, returning deterministic vectors."""

    def __init__(self):
        self.calls: list[list[str]] = []

    async def create(self, model: str, input: list[str]):
        self.calls.append(list(input))
        return FakeEmbeddingResponse(
            [
                FakeEmbeddingItem(index=i, embedding=fake_embedding(text))
                for i, text in enumerate(input)
            ]
        )


class FakeEmbeddingResponse:
    def __init__(self, data):
        self.data = data


class FakeEmbeddingItem:
    def __init__(self, index: int, embedding: list[float]):
        self.index = index
        self.embedding = embedding


class FakeAIClient:
    def __init__(self):
        self.embeddings = FakeEmbeddings()

    @property
    def embedded_texts(self) -> list[str]:
        return [text for call in self.embeddings.calls for text in call]


def fake_embedding(text: str) -> list[float]:
    """A stable, text-dependent unit-ish vector of the configured dimension."""
    dimensions = settings.embedding_dimensions
    vector = [0.0] * dimensions
    for i, char in enumerate(text):
        vector[i % dimensions] += ord(char) / 1000.0
    return vector


@pytest.fixture(scope="session")
def postgres_url() -> str:
    """A throwaway pgvector Postgres with the production schema applied."""
    with PostgresContainer("pgvector/pgvector:pg17", driver=None) as postgres:
        url = postgres.get_connection_url()
        exit_code, output = postgres.exec(
            [
                "psql",
                "-U",
                postgres.username,
                "-d",
                postgres.dbname,
                "-v",
                "ON_ERROR_STOP=1",
                "-c",
                SCHEMA_FILE.read_text(),
            ]
        )
        assert exit_code == 0, f"schema load failed: {output.decode()}"
        yield url


@pytest.fixture
async def pool(postgres_url: str) -> AsyncConnectionPool:
    """An open pool against the container, with the tables emptied first."""
    async with AsyncConnectionPool(postgres_url, min_size=1, open=False) as pool:
        await pool.open()
        await pool.wait()
        async with pool.connection() as conn:
            await conn.execute("TRUNCATE documents, ingested_files RESTART IDENTITY")
            await conn.commit()
        yield pool


@pytest.fixture
def client() -> FakeAIClient:
    return FakeAIClient()


@pytest.fixture
def docs_dir(tmp_path: Path) -> Path:
    (tmp_path / "guide.md").write_text("# Guide\n\nHow to do the thing.\n")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "page.html").write_text(
        "<html><body><p>Hypertext content.</p></body></html>"
    )
    return tmp_path


async def fetch_all(pool: AsyncConnectionPool, sql: str, params=None) -> list[tuple]:
    async with pool.connection() as conn:
        cursor = await conn.execute(sql, params)
        return await cursor.fetchall()


async def test_ingest_documents_persists_a_row_per_chunk(pool, client, docs_dir):
    # Act
    await ingest_documents(str(docs_dir), client, pool)

    # Assert
    rows = await fetch_all(
        pool,
        """
        SELECT source_file, chunk_index, content, vector_dims(embedding)
        FROM documents ORDER BY source_file, chunk_index
        """,
    )
    assert {(row[0], row[1]) for row in rows} == {
        ((docs_dir / "guide.md").as_posix(), 0),
        ((docs_dir / "nested" / "page.html").as_posix(), 0),
    }
    assert "How to do the thing." in "\n".join(row[2] for row in rows)
    assert "Hypertext content." in "\n".join(row[2] for row in rows)
    assert all(row[3] == settings.embedding_dimensions for row in rows)


async def test_ingest_documents_records_each_file_with_its_chunk_count(
    pool, client, docs_dir
):
    # Act
    await ingest_documents(str(docs_dir), client, pool)

    # Assert
    rows = await fetch_all(
        pool,
        """
        SELECT i.source_file, i.chunk_count, count(d.id)
        FROM ingested_files i JOIN documents d ON d.source_file = i.source_file
        GROUP BY i.source_file, i.chunk_count
        """,
    )
    assert len(rows) == 2
    assert all(chunk_count == actual for _, chunk_count, actual in rows)


async def test_ingest_documents_skips_files_already_ingested(pool, client, docs_dir):
    # Arrange
    await ingest_documents(str(docs_dir), client, pool)
    first_pass_texts = list(client.embedded_texts)

    # Act
    await ingest_documents(str(docs_dir), client, pool)

    # Assert
    assert client.embedded_texts == first_pass_texts
    rows = await fetch_all(pool, "SELECT count(*) FROM documents")
    assert rows[0][0] == len(first_pass_texts)


async def test_ingest_documents_reingests_a_file_whose_content_changed(
    pool, client, docs_dir
):
    # Arrange
    await ingest_documents(str(docs_dir), client, pool)
    guide = docs_dir / "guide.md"
    original_hash = await fetch_all(
        pool,
        "SELECT content_hash FROM ingested_files WHERE source_file = %s",
        (guide.as_posix(),),
    )
    guide.write_text("# Guide\n\nHow to do the *other* thing.\n")

    # Act
    await ingest_documents(str(docs_dir), client, pool)

    # Assert
    rows = await fetch_all(
        pool,
        "SELECT content FROM documents WHERE source_file = %s ORDER BY chunk_index",
        (guide.as_posix(),),
    )
    assert "*other* thing" in rows[0][0]
    updated_hash = await fetch_all(
        pool,
        "SELECT content_hash FROM ingested_files WHERE source_file = %s",
        (guide.as_posix(),),
    )
    assert updated_hash != original_hash


async def test_ingest_documents_ignores_unsupported_file_types(pool, client, docs_dir):
    # Arrange
    (docs_dir / "notes.pdf").write_text("binary-ish content")

    # Act
    await ingest_documents(str(docs_dir), client, pool)

    # Assert
    rows = await fetch_all(
        pool, "SELECT count(*) FROM documents WHERE source_file LIKE '%%.pdf'"
    )
    assert rows[0][0] == 0


async def test_ingested_embeddings_are_searchable_by_cosine_distance(
    pool, client, docs_dir
):
    # Arrange
    await ingest_documents(str(docs_dir), client, pool)
    query = str(fake_embedding("Hypertext content."))

    # Act
    rows = await fetch_all(
        pool,
        "SELECT source_file FROM documents ORDER BY embedding <=> %s::vector LIMIT 1",
        (query,),
    )

    # Assert
    assert rows[0][0] == (docs_dir / "nested" / "page.html").as_posix()


async def test_shorter_file_removes_old_chunks(pool, client, tmp_path):
    path = tmp_path / "shrinking.md"
    path.write_text(("A paragraph of text. " * 50 + "\n\n") * 6)
    await ingest_file(path, client, pool)
    before = await fetch_all(pool, "SELECT count(*) FROM documents")
    assert before[0][0] > 1
    path.write_text("Short replacement.")
    await ingest_file(path, client, pool)
    rows = await fetch_all(pool, "SELECT content FROM documents")
    assert rows == [("Short replacement.",)]


async def test_embedding_failure_preserves_existing_file(pool, client, tmp_path, monkeypatch):
    path = tmp_path / "stable.md"
    path.write_text("Original content.")
    await ingest_file(path, client, pool)
    path.write_text("Changed content.")

    async def fail(**kwargs):
        raise RuntimeError("embedding failure")

    monkeypatch.setattr(client.embeddings, "create", fail)
    with pytest.raises(RuntimeError, match="embedding failure"):
        await ingest_file(path, client, pool)
    assert await fetch_all(pool, "SELECT content FROM documents") == [("Original content.",)]
