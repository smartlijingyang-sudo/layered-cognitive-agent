"""Full-text memory index port.

The retrieval decision tree needs a real index over curated memory and trail
files. ``MemoryIndex`` is the replaceable seam: a SQLite FTS backend is the
default adapter, tests can use an in-memory one, and the domain never touches
SQL.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class IndexedDocument:
    """One searchable document."""

    doc_id: str
    kind: str
    content: str
    path: str


@runtime_checkable
class MemoryIndex(Protocol):
    """Build and query a full-text index."""

    def rebuild(self, documents: list[IndexedDocument]) -> None: ...
    def search(self, query: str, *, limit: int) -> list[IndexedDocument]: ...
    def close(self) -> None: ...


__all__ = ["IndexedDocument", "MemoryIndex"]
