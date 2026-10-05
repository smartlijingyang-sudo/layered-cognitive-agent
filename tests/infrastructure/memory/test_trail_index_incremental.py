"""trail 的增量索引与全量重建产出同一个文档。

`_documents` 按**整个流水文件**产一个文档，`doc_id=trail-<文件名>`，不是按行。
增量写入必须用同一形状，否则一次全量重建会为同一天留下两个文档，或者把增量
写进去的那个孤立掉。
"""

from __future__ import annotations

from pathlib import Path

from lca.infrastructure.memory.contextfiles.adapters.disk import DiskFileStore
from lca.infrastructure.memory.contextfiles.adapters.fts import SqliteFtsIndex
from lca.infrastructure.memory.contextfiles.domain.layout import packaged_layout
from lca.infrastructure.memory.contextfiles.ports.memory_index import IndexedDocument
from lca.infrastructure.memory.contextfiles.service.indexing import (
    build_memory_index,
    index_trail_file,
    search_memory_index,
)

_DATE = "2026-10-05"


def _write_trail(home: Path, *lines: str) -> None:
    (home / "memory").mkdir(parents=True, exist_ok=True)
    body = "".join(f"- {line}\n" for line in lines)
    (home / "memory" / f"{_DATE}.md").write_text(f"# {_DATE}\n\n{body}", encoding="utf-8")


def test_add_upserts_rather_than_duplicates(tmp_path: Path) -> None:
    db = tmp_path / "index" / "fts.sqlite3"
    index = SqliteFtsIndex(db)
    try:
        doc = IndexedDocument(doc_id="d1", kind="trail", content="第一版", path="memory/x.md")
        index.add(doc)
        index.add(IndexedDocument(doc_id="d1", kind="trail", content="第二版", path="memory/x.md"))
        hits = index.search("第二版", limit=10)
    finally:
        index.close()

    assert [h.doc_id for h in hits] == ["d1"]
    assert hits[0].content == "第二版"


def test_incremental_document_matches_the_full_rebuild(tmp_path: Path) -> None:
    """核心一致性保证：同一天在两种写法下 doc_id / kind / path 完全相同。"""
    home = tmp_path / "asst"
    _write_trail(home, "还是简洁一点好")

    assert index_trail_file(home, DiskFileStore(home), _DATE) is True
    incremental = search_memory_index(home, "简洁", limit=10)

    rebuilt_home = tmp_path / "rebuilt"
    _write_trail(rebuilt_home, "还是简洁一点好")
    build_memory_index(rebuilt_home, DiskFileStore(rebuilt_home), [])
    rebuilt = search_memory_index(rebuilt_home, "简洁", limit=10)

    assert incremental is not None and rebuilt is not None
    assert [(d.doc_id, d.kind, d.path) for d in incremental] == [
        (d.doc_id, d.kind, d.path) for d in rebuilt
    ]
    assert incremental[0].doc_id == f"trail-{_DATE}.md"


def test_second_append_replaces_the_same_document(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    _write_trail(home, "还是简洁一点好")
    index_trail_file(home, DiskFileStore(home), _DATE)

    (home / "memory" / f"{_DATE}.md").write_text(
        f"# {_DATE}\n\n- 还是简洁一点好\n- 另外别用 emoji\n", encoding="utf-8"
    )
    index_trail_file(home, DiskFileStore(home), _DATE)

    hits = search_memory_index(home, "简洁", limit=10) or []
    assert len(hits) == 1
    assert "别用 emoji" in hits[0].content


def test_missing_trail_file_returns_false(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    (home / "memory").mkdir(parents=True)

    assert index_trail_file(home, DiskFileStore(home), _DATE) is False


def test_empty_trail_file_returns_false_and_creates_no_index(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    (home / "memory").mkdir(parents=True)
    (home / "memory" / f"{_DATE}.md").write_text("", encoding="utf-8")

    assert index_trail_file(home, DiskFileStore(home), _DATE) is False
    assert not (home / packaged_layout().index_db_path).exists()
