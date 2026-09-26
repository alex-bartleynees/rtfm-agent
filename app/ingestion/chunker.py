import logging
import os
from fnmatch import fnmatchcase
from collections.abc import Iterator
from pathlib import Path

from bs4 import BeautifulSoup

from app.config import settings
from app.ingestion.models import Chunk

logger = logging.getLogger(__name__)


def is_ignored(path: Path, docs_dir: Path) -> bool:
    """Match names at any depth, or slash-containing globs relative to the root."""
    try:
        relative = path.absolute().relative_to(docs_dir.absolute())
    except ValueError:
        return True
    candidates = [relative, *relative.parents]
    for pattern in settings.docs_ignore_patterns:
        pattern = pattern.rstrip("/")
        if not pattern:
            continue
        for candidate in candidates:
            value = candidate.as_posix() if "/" in pattern else candidate.name
            if fnmatchcase(value, pattern):
                return True
    return False


def iter_files(docs_dir: Path) -> Iterator[Path]:
    """Recursively iterate through all files in the given directory."""
    def raise_walk_error(error):
        raise error

    if not docs_dir.is_dir():
        raise FileNotFoundError(f"Document directory does not exist: {docs_dir}")
    for directory, dirs, files in os.walk(docs_dir, onerror=raise_walk_error):
        parent = Path(directory)
        dirs[:] = [name for name in dirs if not is_ignored(parent / name, docs_dir)]
        for name in files:
            path = parent / name
            if not is_ignored(path, docs_dir) and path.suffix[1:] in settings.supported_file_types:
                yield path


def extract_text_from_file(file_path: Path) -> str | None:
    """Extract text content from a file based on its type."""
    logger.debug("Extracting text from file: %s", file_path)
    if file_path.suffix[1:] in settings.plain_text_formats:
        return read_file(file_path)
    elif file_path.suffix[1:] in settings.markup_formats:
        html_content = read_file(file_path)
        if html_content is not None:
            soup = BeautifulSoup(html_content, "html.parser")
            return soup.get_text()

    return None


def read_file(file_path: Path) -> str | None:
    """Read a file and extract its text content."""
    try:
        return file_path.read_text(encoding="utf-8")
    except Exception:
        logger.exception("Error reading file %s", file_path)
        return None


def chunk_text(source: Path, text: str) -> Iterator[Chunk]:
    """Return an iterator that yields chunks of the given text with specified size and overlap."""
    # Split text on \n\n to preserve paragraphs
    logger.debug("Chunking text from %s", source)
    paragraphs = text.split("\n\n")
    current_chunk = ""
    position = 0
    chunk_size = (
        settings.chunk_size * 4
    )  # Approximate character count (assuming average 4 chars per token)
    chunk_overlap = (
        settings.chunk_overlap * 4
    )  # Approximate character count for overlap

    for paragraph in paragraphs:
        if len(paragraph) > chunk_size:
            # Split the paragraph into smaller chunks
            start = 0
            while start < len(paragraph):
                end = min(start + chunk_size, len(paragraph))
                sub_chunk = paragraph[start:end]
                yield Chunk(
                    text=sub_chunk.strip(),
                    source=source,
                    position=position,
                )
                position += 1
                start += chunk_size - chunk_overlap
            continue
        if len(current_chunk) + len(paragraph) + 2 >= chunk_size:
            yield Chunk(
                text=current_chunk.strip(),
                source=source,
                position=position,
            )
            position += 1
            current_chunk = current_chunk[-chunk_overlap:] + paragraph + "\n\n"
        else:
            current_chunk += paragraph + "\n\n"

    # Process any remaining text
    current_chunk = current_chunk.strip()
    if current_chunk:
        yield Chunk(text=current_chunk, source=source, position=position)
