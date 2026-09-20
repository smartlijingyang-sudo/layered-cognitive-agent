"""PR-2（ADR-0246）：memory harness 写→检索→supersede 全流程测试。"""

from __future__ import annotations

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord
from tests.support.memory_harness import InMemoryMemoryStore


def _record(
    record_id: str, *, category: MemoryCategory, content: str, dedupe_key: str
) -> MemoryRecord:
    return MemoryRecord(
        record_id=record_id,
        content=content,
        memory_type=MemoryLayer.SEMANTIC,
        importance=0.8,
        category=category,
        dedupe_key=dedupe_key,
        created_at_ms=1,
    )


def test_upsert_query_roundtrip() -> None:
    store = InMemoryMemoryStore()
    record = _record(
        "mem_1",
        category=MemoryCategory.IDENTITY,
        content="用户身份：架构师",
        dedupe_key="identity:architect",
    )
    store.upsert(record)

    results = store.query(category=MemoryCategory.IDENTITY)
    assert len(results) == 1
    assert results[0].content == "用户身份：架构师"


def test_upsert_same_dedupe_key_supersedes_old() -> None:
    store = InMemoryMemoryStore()
    old = _record(
        "mem_1",
        category=MemoryCategory.IDENTITY,
        content="用户身份：架构师",
        dedupe_key="identity:architect",
    )
    store.upsert(old)

    new = _record(
        "mem_2",
        category=MemoryCategory.IDENTITY,
        content="用户身份：架构师（已确认）",
        dedupe_key="identity:architect",
    )
    store.upsert(new)

    # 默认查询排除被 supersede 的旧记录
    active = store.query(category=MemoryCategory.IDENTITY)
    assert [r.record_id for r in active] == ["mem_2"]
    assert active[0].revision_of == "mem_1"

    # 包含 superseded 时旧记录可见且被标记
    all_records = store.query(category=MemoryCategory.IDENTITY, include_superseded=True)
    by_id = {r.record_id: r for r in all_records}
    assert by_id["mem_1"].deleted is True
    assert by_id["mem_1"].retired_at_ms is not None


def test_supersede_marks_old_and_links_replacement() -> None:
    store = InMemoryMemoryStore()
    old = _record(
        "mem_a",
        category=MemoryCategory.PREFERENCE,
        content="用户偏好：不喜欢啰嗦",
        dedupe_key="preference:concise",
    )
    store.upsert(old)
    replacement = _record(
        "mem_b",
        category=MemoryCategory.PREFERENCE,
        content="用户偏好：简洁回复",
        dedupe_key="preference:concise",
    )
    store.supersede("mem_a", replacement)

    active = store.query(category=MemoryCategory.PREFERENCE)
    assert [r.record_id for r in active] == ["mem_b"]
    assert active[0].revision_of == "mem_a"


def test_query_filters_by_category() -> None:
    store = InMemoryMemoryStore()
    store.upsert(
        _record("mem_id", category=MemoryCategory.IDENTITY, content="身份", dedupe_key="id1")
    )
    store.upsert(
        _record("mem_pref", category=MemoryCategory.PREFERENCE, content="偏好", dedupe_key="p1")
    )

    assert [r.record_id for r in store.query(category=MemoryCategory.IDENTITY)] == ["mem_id"]
    assert [r.record_id for r in store.query(category=MemoryCategory.PREFERENCE)] == ["mem_pref"]
    assert len(store.query()) == 2
