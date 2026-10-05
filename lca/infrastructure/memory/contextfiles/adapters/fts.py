"""SQLite full-text index adapter for ``MemoryIndex``.

Uses FTS5 when the stdlib SQLite build provides it and falls back to a plain
table with LIKE scanning otherwise, so the adapter works on any host. CJK
text is stored with every ideograph space-separated because the ``unicode61``
tokenizer treats a CJK run as one token; separating the ideographs lets a
multi-character Chinese query match the same way a substring search would.
The database lives at ``memory/index/fts.sqlite3`` under the assistant home.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from lca.infrastructure.memory.contextfiles.domain.search import fts_query, tokenize
from lca.infrastructure.memory.contextfiles.ports.memory_index import IndexedDocument

_FTS_TABLE = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5("
    "searchable, kind, path, doc_id UNINDEXED, original UNINDEXED)"
)
_PLAIN_TABLE = (
    "CREATE TABLE IF NOT EXISTS memory_docs (doc_id TEXT, kind TEXT, content TEXT, path TEXT)"
)


def _searchable(text: str) -> str:
    """Space-separate CJK ideographs so FTS5 can match Chinese queries."""

    return " ".join(tokenize(text))


class SqliteFtsIndex:
    """``MemoryIndex`` backed by a SQLite database file."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(self._db_path))
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._fts5 = self._probe_fts5()
        self._connection.execute(_FTS_TABLE if self._fts5 else _PLAIN_TABLE)
        self._connection.commit()

    def _probe_fts5(self) -> bool:
        try:
            self._connection.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_probe USING fts5(x)")
            self._connection.execute("DROP TABLE IF EXISTS _fts5_probe")
            return True
        except sqlite3.OperationalError:
            return False

    def rebuild(self, documents: list[IndexedDocument]) -> None:
        """Replace the index with ``documents``."""

        self._connection.execute("DROP TABLE IF EXISTS memory_fts")
        self._connection.execute("DROP TABLE IF EXISTS memory_docs")
        self._connection.execute(_FTS_TABLE if self._fts5 else _PLAIN_TABLE)
        if self._fts5:
            self._connection.executemany(
                "INSERT INTO memory_fts(searchable, kind, path, doc_id, original)"
                " VALUES (?, ?, ?, ?, ?)",
                [
                    (_searchable(doc.content), doc.kind, doc.path, doc.doc_id, doc.content)
                    for doc in documents
                ],
            )
        else:
            self._connection.executemany(
                "INSERT INTO memory_docs(doc_id, kind, content, path) VALUES (?, ?, ?, ?)",
                [(doc.doc_id, doc.kind, doc.content, doc.path) for doc in documents],
            )
        self._connection.commit()

    def add(self, document: IndexedDocument) -> None:
        """Insert or replace one document, keyed by ``doc_id``."""

        if self._fts5:
            self._connection.execute("DELETE FROM memory_fts WHERE doc_id = ?", (document.doc_id,))
            self._connection.execute(
                "INSERT INTO memory_fts(searchable, kind, path, doc_id, original)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    _searchable(document.content),
                    document.kind,
                    document.path,
                    document.doc_id,
                    document.content,
                ),
            )
        else:
            self._connection.execute("DELETE FROM memory_docs WHERE doc_id = ?", (document.doc_id,))
            self._connection.execute(
                "INSERT INTO memory_docs(doc_id, kind, content, path) VALUES (?, ?, ?, ?)",
                (document.doc_id, document.kind, document.content, document.path),
            )
        self._connection.commit()

    def search(self, query: str, *, limit: int) -> list[IndexedDocument]:
        """Return up to ``limit`` documents matching ``query``."""

        if self._fts5:
            return self._search_fts(query, limit=limit)
        return self._search_plain(query, limit=limit)

    def _search_fts(self, query: str, *, limit: int) -> list[IndexedDocument]:
        match = fts_query(tokenize(query))
        rows = self._connection.execute(
            "SELECT doc_id, kind, original, path FROM memory_fts WHERE memory_fts MATCH ? LIMIT ?",
            (match, limit),
        ).fetchall()
        return [
            IndexedDocument(
                doc_id=str(row[0]), kind=str(row[1]), content=str(row[2]), path=str(row[3])
            )
            for row in rows
        ]

    def _search_plain(self, query: str, *, limit: int) -> list[IndexedDocument]:
        if not query.strip():
            return []
        rows = self._connection.execute(
            "SELECT doc_id, kind, content, path FROM memory_docs WHERE content LIKE ? LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
        return [
            IndexedDocument(
                doc_id=str(row[0]), kind=str(row[1]), content=str(row[2]), path=str(row[3])
            )
            for row in rows
        ]

    def close(self) -> None:
        self._connection.close()


__all__ = ["SqliteFtsIndex"]
