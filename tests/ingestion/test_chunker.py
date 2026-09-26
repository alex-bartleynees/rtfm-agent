from pathlib import Path
from unittest.mock import MagicMock

import pytest

@pytest.fixture()
def mock_settings(mocker):
    fake = MagicMock()
    fake.chunk_size = 10        # 10 tokens → ~40 chars
    fake.chunk_overlap = 2      # 2 tokens → ~8 chars
    fake.plain_text_formats = ["txt", "md"]
    fake.markup_formats = ["html"]
    fake.supported_file_types = ["txt", "md", "html"]
    mocker.patch("app.ingestion.chunker.settings", fake)
    return fake


from app.ingestion.chunker import chunk_text, extract_text_from_file, iter_files  # noqa: E402


def test_chunk_text_single_chunk():
    # Arrange
    source = Path("doc.md")
    text = "Hello world."

    # Act
    chunks = list(chunk_text(source, text))

    # Assert
    assert len(chunks) == 1
    assert chunks[0].text == "Hello world."
    assert chunks[0].source == source
    assert chunks[0].position == 0


def test_chunk_text_splits_on_double_newline(mock_settings):
    # Arrange
    mock_settings.chunk_size = 5
    mock_settings.chunk_overlap = 1 
    source = Path("doc.md")
    text = "First paragraph.\n\nSecond paragraph."

    # Act
    chunks = list(chunk_text(source, text))

    # Assert
    assert len(chunks) == 2
    assert chunks[0].text == "First paragraph."
    assert "Second paragraph." in chunks[1].text
    assert chunks[0].position == 0
    assert chunks[1].position == 1


def test_chunk_text_overlap_carries_tail(mock_settings):
    # Arrange
    mock_settings.chunk_size = 3 
    mock_settings.chunk_overlap = 2 
    source = Path("doc.md")
    text = "AAAAAAAAAA\n\nBBBBBBBBBB\n\nCCCCCCCCCC"

    # Act
    chunks = list(chunk_text(source, text))

    # Assert
    assert chunks[1].text.startswith(chunks[0].text[-8:].strip())

def test_chunk_text_without_double_newline(mock_settings):
    # Arrange
    mock_settings.chunk_size = 3
    mock_settings.chunk_overlap = 2
    source = Path("doc.md")
    text = "This is a long text without double newlines.Let's see how it gets chunked.Let's see how it gets chunked.Let's see how it gets chunked."
    max_chars = mock_settings.chunk_size * 4

    # Act
    chunks = list(chunk_text(source, text))

    # Assert
    for chunk in chunks:
        assert len(chunk.text) <= max_chars 


def test_chunk_text_empty_string():
    # Arrange
    source = Path("doc.md")
    text = ""

    # Act
    chunks = list(chunk_text(source, text))

    # Assert
    assert chunks == []


def test_extract_text_plain(tmp_path):
    # Arrange
    f = tmp_path / "notes.txt"
    f.write_text("Hello from a txt file.", encoding="utf-8")

    # Act
    result = extract_text_from_file(f)

    # Assert
    assert result == "Hello from a txt file."


def test_extract_text_html_strips_tags(tmp_path):
    # Arrange
    f = tmp_path / "page.html"
    f.write_text("<html><body><p>Hello</p></body></html>", encoding="utf-8")

    # Act
    result = extract_text_from_file(f)

    # Assert
    assert result is not None
    assert "<p>" not in result
    assert "Hello" in result


def test_extract_text_unsupported_returns_none(tmp_path):
    # Arrange
    f = tmp_path / "data.csv"
    f.write_text("a,b,c", encoding="utf-8")

    # Act
    result = extract_text_from_file(f)

    # Assert
    assert result is None


def test_iter_files_yields_supported(tmp_path):
    # Arrange
    (tmp_path / "a.md").write_text("x")
    (tmp_path / "b.txt").write_text("x")
    (tmp_path / "ignore.csv").write_text("x")

    # Act
    found = {p.name for p in iter_files(tmp_path)}

    # Assert
    assert found == {"a.md", "b.txt"}


def test_iter_files_recurses(tmp_path):
    # Arrange
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "deep.md").write_text("x")

    # Act
    found = list(iter_files(tmp_path))

    # Assert
    assert any(p.name == "deep.md" for p in found)
