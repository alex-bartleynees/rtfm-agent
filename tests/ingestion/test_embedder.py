from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from app.ingestion.embedder import embed_chunks

import pytest

@pytest.mark.asyncio
async def test_embed_chunks_yields_embedded_chunks():
    # Arrange
    mock_client = MagicMock()
    mock_embeddings = MagicMock()
    mock_embeddings.data = [
        MagicMock(index=0, embedding=[0.1, 0.2]),
        MagicMock(index=1, embedding=[0.3, 0.4]),
    ]
    mock_client.embeddings.create = AsyncMock(return_value=mock_embeddings)

    chunks = [
        MagicMock(text="Chunk 1", source=Path("doc.md"), position=0),
        MagicMock(text="Chunk 2", source=Path("doc.md"), position=1),
    ]

    # Act

    embedded_chunks = [chunk async for chunk in embed_chunks(chunks, mock_client)] 

    # Assert
    assert len(embedded_chunks) == 2
    assert embedded_chunks[0].text == "Chunk 1"
    assert embedded_chunks[0].embedding == [0.1, 0.2]
    assert embedded_chunks[1].text == "Chunk 2"
    assert embedded_chunks[1].embedding == [0.3, 0.4]

@pytest.mark.asyncio
async def test_embed_chunks_should_handle_empty_chunks():
    # Arrange
    mock_client = MagicMock()
    mock_client.embeddings.create = AsyncMock()

    chunks = []

    # Act
    embedded_chunks = [chunk async for chunk in embed_chunks(chunks, mock_client)]

    # Assert
    assert len(embedded_chunks) == 0
    mock_client.embeddings.create.assert_not_called()

@pytest.mark.asyncio
async def test_embed_chunks_should_batch_chunks_when_more_than_batch_size():
    # Arrange
    mock_client = MagicMock()
    mock_embeddings = MagicMock()
    first_response = [MagicMock(index=i, embedding=[i * 0.1, i * 0.2]) for i in range(32)]
    second_response = [MagicMock(index=i, embedding=[i * 0.1, i * 0.2]) for i in range(0, 3)]
    mock_embeddings.data = [*first_response, *second_response]
    mock_client.embeddings.create = AsyncMock(side_effect=[MagicMock(data=first_response), MagicMock(data=second_response)])  # Simulate two batches

    chunks = [
        MagicMock(text=f"Chunk {i}", source=Path("doc.md"), position=i) for i in range(35)
    ]

    # Act
    embedded_chunks = [chunk async for chunk in embed_chunks(chunks, mock_client)]

    # Assert
    assert len(embedded_chunks) == 35
    assert mock_client.embeddings.create.call_count == 2 