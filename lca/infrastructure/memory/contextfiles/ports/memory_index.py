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
    def add(self, document: IndexedDocument) -> None:
        """Insert or replace one document, keyed by ``doc_id``.

        Callers that write incrementally must produce the same ``doc_id`` and
        field shape ``rebuild`` would, or a later full rebuild leaves two
        documents for one subject.
        """
        ...

    def search(self, query: str, *, limit: int) -> list[IndexedDocument]: ...
    def close(self) -> None: ...


__all__ = ["IndexedDocument", "MemoryIndex"]
