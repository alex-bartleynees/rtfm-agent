import logging
from collections.abc import Iterator
from pathlib import Path

logger = logging.getLogger(__name__)

from bs4 import BeautifulSoup

from app.config import settings


def iter_files(docs_dir: Path) -> Iterator[Path]:
    """Recursively iterate through all files in the given directory."""
    for path in docs_dir.rglob("*"):
        if path.is_file():
            if path.suffix[1:] in settings.supported_file_types:
                yield path


def extract_text_from_file(file_path: Path) -> str | None:
    """Extract text content from a file based on its type."""
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
    except Exception as e:
        logger.exception("Error reading file %s", file_path)
        return None

def chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
