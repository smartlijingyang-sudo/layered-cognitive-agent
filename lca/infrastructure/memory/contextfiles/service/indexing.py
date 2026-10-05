"""Build and query the full-text memory index under ``memory/index``.

The index is a projection over curated semantic records and the daily trail
flow. It is rebuildable at any time and never becomes a source of truth. The
``MemoryIndex`` port keeps the backend replaceable. The package stays movable:
semantic records are supplied by the caller, so this module never imports the
host record store.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Sequence
from pathlib import Path

from lca.infrastructure.memory.contextfiles.adapters.fts import SqliteFtsIndex
from lca.infrastructure.memory.contextfiles.domain.layout import ContextLayout, packaged_layout
from lca.infrastructure.memory.contextfiles.events.publisher import IndexRebuilt
from lca.infrastructure.memory.contextfiles.ports.events import DomainEventPublisher
from lca.infrastructure.memory.contextfiles.ports.file_store import FileStore
from lca.infrastructure.memory.contextfiles.ports.memory_index import IndexedDocument

logger = logging.getLogger(__name__)


def build_memory_index(
    home: str | Path,
    store: FileStore,
    records: Sequence[object],
    *,
    layout: ContextLayout | None = None,
    publisher: DomainEventPublisher | None = None,
) -> int:
    """Rebuild the full-text index from curated records and trail files.

    ``records`` supplies the curated semantic rows; each object exposes
    ``record_id`` and ``content``. Returns the number of indexed documents.
    """

    chosen = packaged_layout() if layout is None else layout
    documents = _documents(home, store, records, layout=chosen)
    index = SqliteFtsIndex(Path(home) / chosen.index_db_path)
    try:
        index.rebuild(documents)
    finally:
        index.close()
    logger.info("memory index rebuilt home=%s documents=%s", home, len(documents))
    if publisher is not None:
        publisher.publish(
            IndexRebuilt(
                path=chosen.index_db_path,
                document_count=len(documents),
            )
        )
    return len(documents)


def search_memory_index(
    home: str | Path,
    query: str,
    *,
    limit: int = 5,
    layout: ContextLayout | None = None,
) -> list[IndexedDocument] | None:
    """Search the built index. Returns ``None`` when no index exists yet."""

    chosen = packaged_layout() if layout is None else layout
    db_path = Path(home) / chosen.index_db_path
    if not db_path.is_file():
        return None
    index = SqliteFtsIndex(db_path)
    try:
        return index.search(query, limit=max(1, min(50, limit)))
    finally:
        index.close()


def _documents(
    home: str | Path,
    store: FileStore,
    records: Sequence[object],
    *,
    layout: ContextLayout,
) -> list[IndexedDocument]:
    documents: list[IndexedDocument] = []
    for record in records:
        content = str(getattr(record, "content", "") or "").strip()
        if not content:
            continue
        documents.append(
            IndexedDocument(
                doc_id=str(getattr(record, "record_id", "") or f"mem-{len(documents)}"),
                kind="semantic",
                content=content,
                path="memory/semantic.json",
            )
        )
    for name in store.list_dir(layout.trail_dir):
        if not name.endswith(".md"):
            continue
        try:
            text = store.read_text(f"{layout.trail_dir}/{name}")
        except OSError:
            continue
        documents.append(_trail_document(name, text, layout=layout))
    return documents


def _trail_document(name: str, text: str, *, layout: ContextLayout) -> IndexedDocument:
    """One day's trail as a single index document.

    Shared by the full rebuild and the incremental write so the two cannot
    disagree about ``doc_id``, ``kind``, or ``path`` for the same day.
    """

    return IndexedDocument(
        doc_id=f"trail-{name}",
        kind="trail",
        content=text,
        path=f"{layout.trail_dir}/{name}",
    )


def index_trail_file(
    home: str | Path,
    store: FileStore,
    date: str,
    *,
    layout: ContextLayout | None = None,
) -> bool:
    """Re-index one day's trail document after an append.

    The caller has already made the trail durable, so failure here is contained
    and reported as False rather than raised. The index is a rebuildable
    projection and the next ``run_dream`` full rebuild is the backstop.
    """

    chosen = packaged_layout() if layout is None else layout
    name = f"{date}.md"
    try:
        text = store.read_text(f"{chosen.trail_dir}/{name}")
    except OSError:
        return False
    if not text.strip():
        return False
    db_path = Path(home) / chosen.index_db_path
    index = SqliteFtsIndex(db_path)
    try:
        index.add(_trail_document(name, text, layout=chosen))
    except (sqlite3.Error, OSError) as exc:
        logger.warning("trail index write failed path=%s: %s", db_path, exc)
        return False
    finally:
        index.close()
    return True


__all__ = ["build_memory_index", "index_trail_file", "search_memory_index"]
