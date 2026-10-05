"""流水索引按行粒度，且增量写入与全量重建产出同一批文档。

`_documents` 与 `index_trail_line` 是两个生产方对着同一个消费方
`search_memory_index`。两者的 `doc_id` 必须逐字段一致，否则一次全量重建会把增量
写进去的文档孤立掉，或者同一行留下两个文档。

粒度是行不是天。按天产文档时一次命中会把整天原文送进模型上下文，生产上实测
三个不相关的查询返回同一个 623 字符的整日文档。
"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.mechanisms.content.addressable import sha256_hex
from lca.infrastructure.memory.contextfiles.adapters.disk import DiskFileStore
from lca.infrastructure.memory.contextfiles.adapters.fts import SqliteFtsIndex
from lca.infrastructure.memory.contextfiles.domain.layout import packaged_layout
from lca.infrastructure.memory.contextfiles.ports.memory_index import IndexedDocument
from lca.infrastructure.memory.contextfiles.service.indexing import (
    build_memory_index,
    index_trail_line,
    search_memory_index,
)

_DATE = "2026-10-05"
_LINE_A = "还是简洁一点好"
_LINE_B = "以后不要用 emoji"


def _expected_doc_id(date: str, line: str) -> str:
    return f"trail-{date}-{sha256_hex(line.encode('utf-8'), length=12)}"


def _write_trail(home: Path, *lines: str) -> None:
    (home / "memory").mkdir(parents=True, exist_ok=True)
    body = "".join(f"- {line}\n" for line in lines)
    (home / "memory" / f"{_DATE}.md").write_text(f"# {_DATE}\n\n{body}", encoding="utf-8")


def _shapes(hits: list[IndexedDocument]) -> list[tuple[str, str, str, str]]:
    return sorted((h.doc_id, h.kind, h.path, h.content) for h in hits)


def test_add_upserts_rather_than_duplicates(tmp_path: Path) -> None:
    db = tmp_path / "index" / "fts.sqlite3"
    index = SqliteFtsIndex(db)
    try:
        index.add(IndexedDocument(doc_id="d1", kind="trail", content="第一版", path="memory/x.md"))
        index.add(IndexedDocument(doc_id="d1", kind="trail", content="第二版", path="memory/x.md"))
        hits = index.search("第二版", limit=10)
    finally:
        index.close()

    assert [h.doc_id for h in hits] == ["d1"]
    assert hits[0].content == "第二版"


def test_full_rebuild_emits_one_document_per_line(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    _write_trail(home, _LINE_A, _LINE_B)

    count = build_memory_index(home, DiskFileStore(home), [])

    assert count == 2
    hits = search_memory_index(home, "简洁", limit=10) or []
    assert len(hits) == 1
    assert hits[0].content == _LINE_A
    assert hits[0].doc_id == _expected_doc_id(_DATE, _LINE_A)
    assert hits[0].path == f"memory/{_DATE}.md"


def test_incremental_write_matches_the_full_rebuild(tmp_path: Path) -> None:
    """核心一致性保证：同一行经两条路径产出的文档逐字段相同。"""
    incremental_home = tmp_path / "incremental"
    (incremental_home / "memory").mkdir(parents=True)
    assert index_trail_line(incremental_home, _DATE, _LINE_A) is True
    assert index_trail_line(incremental_home, _DATE, _LINE_B) is True
    incremental = search_memory_index(incremental_home, "简洁 emoji", limit=10) or []

    rebuilt_home = tmp_path / "rebuilt"
    _write_trail(rebuilt_home, _LINE_A, _LINE_B)
    build_memory_index(rebuilt_home, DiskFileStore(rebuilt_home), [])
    rebuilt = search_memory_index(rebuilt_home, "简洁 emoji", limit=10) or []

    assert _shapes(incremental) == _shapes(rebuilt)
    assert len(incremental) == 2


def test_repeated_line_does_not_duplicate(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    (home / "memory").mkdir(parents=True)

    assert index_trail_line(home, _DATE, _LINE_A) is True
    assert index_trail_line(home, _DATE, _LINE_A) is True

    hits = search_memory_index(home, "简洁", limit=10) or []
    assert len(hits) == 1


def test_same_line_on_two_days_stays_separate(tmp_path: Path) -> None:
    """日期在 doc_id 里，所以全量重建的 path 不依赖 list_dir 顺序。"""
    home = tmp_path / "asst"
    (home / "memory").mkdir(parents=True)

    index_trail_line(home, "2026-10-04", _LINE_A)
    index_trail_line(home, _DATE, _LINE_A)

    hits = search_memory_index(home, "简洁", limit=10) or []
    assert sorted(h.doc_id for h in hits) == sorted(
        [_expected_doc_id("2026-10-04", _LINE_A), _expected_doc_id(_DATE, _LINE_A)]
    )
    assert sorted(h.path for h in hits) == ["memory/2026-10-04.md", f"memory/{_DATE}.md"]


def test_empty_content_is_not_indexed(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    (home / "memory").mkdir(parents=True)

    assert index_trail_line(home, _DATE, "   ") is False
    assert not (home / packaged_layout().index_db_path).exists()


def test_a_document_is_one_line_not_a_whole_day(tmp_path: Path) -> None:
    """回归锁：命中的 content 不得包含同一天的其他行。"""
    home = tmp_path / "asst"
    _write_trail(home, _LINE_A, "用户住址是杭州市西湖区某路 1 号", _LINE_B)

    build_memory_index(home, DiskFileStore(home), [])
    hits = search_memory_index(home, "简洁", limit=10) or []

    assert len(hits) == 1
    assert hits[0].content == _LINE_A
    assert "住址" not in hits[0].content
