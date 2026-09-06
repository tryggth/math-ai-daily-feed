"""Canonical schema definitions for papers and aggregated feeds."""

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class Paper:
    """Canonical representation of a research paper across pillars."""

    id: str
    title: str
    url: str
    authors: list[str]
    published: str
    summary: str
    source: str
    pillar: str

    def __post_init__(self) -> None:
        # Clean and collapse whitespace to guarantee single-line title
        self.title = " ".join(self.title.split())
        # Clean abstract text
        self.summary = " ".join(self.summary.split())
        # Clean author names
        self.authors = [" ".join(a.split()) for a in self.authors if a and a.strip()]
        # Truncate ISO timestamp to YYYY-MM-DD
        if self.published and len(self.published) >= 10:
            self.published = self.published[:10]

    def to_dict(self) -> dict[str, Any]:
        """Convert Paper instance to a standard dictionary."""
        return asdict(self)

    def __getitem__(self, key: str) -> Any:
        """Support dict-like indexing for compatibility."""
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key)
