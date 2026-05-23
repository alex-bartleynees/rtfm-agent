from dataclasses import dataclass
from pathlib import Path


@dataclass
class Chunk:
    text: str
    source: Path
    position: int
