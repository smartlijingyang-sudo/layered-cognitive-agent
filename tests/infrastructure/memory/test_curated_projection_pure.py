"""Unit tests for the pure functional curated memory markdown projector.

Validates INV-MEM-01 (pure equivalence), INV-MEM-02 (skeleton persistence),
and INV-MEM-03 (category isolation).
"""

from __future__ import annotations

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.infrastructure.memory.contextfiles.domain.curated import (
    render_curated_memory_markdown,
)


def _record(
    *,
    record_id: str,
    content: str,
    category: MemoryCategory = MemoryCategory.FACT,
    importance: float = 0.5,
    source: str = "user",
) -> MemoryRecord:
    return MemoryRecord(
        record_id=record_id,
        content=content,
        memory_type=MemoryLayer.SEMANTIC,
        importance=importance,
        category=category,
        dedupe_key=record_id,
        confidence=1.0,
        metadata={"source": source},
    )


def test_empty_records_retains_skeleton():
    """INV-MEM-02: Skeleton never collapses when records list is empty."""
    text = render_curated_memory_markdown([])
    assert "# 长期记忆" in text
    assert "## Preferences" in text
    assert "## Facts" in text
    assert "（暂无偏好记录）" in text
    assert "（暂无事实记录）" in text


def test_bullet_contains_embedded_id():
    """Every rendered bullet carries <!-- id:mem_xxx --> for deterministic edit sync."""
    records = [
        _record(
            record_id="mem_pref_01",
            content="用户偏好暗色主题",
            category=MemoryCategory.PREFERENCE,
        ),
        _record(
            record_id="mem_fact_02",
            content="开发机IP为10.36.6.252",
            category=MemoryCategory.FACT,
        ),
    ]
    text = render_curated_memory_markdown(records)
    assert "## Preferences" in text
    assert "- 用户偏好暗色主题. This came from user. <!-- id:mem_pref_01 -->" in text or "<!-- id:mem_pref_01 -->" in text
    assert "## Facts" in text
    assert "<!-- id:mem_fact_02 -->" in text


def test_identity_category_excluded():
    """INV-MEM-03: Category 'identity' stays in USER.md and never enters MEMORY.md."""
    records = [
        _record(
            record_id="mem_id_01",
            content="用户性别：男",
            category=MemoryCategory.IDENTITY,
        ),
        _record(
            record_id="mem_fact_01",
            content="首选语言是Python",
            category=MemoryCategory.FACT,
        ),
    ]
    text = render_curated_memory_markdown(records)
    assert "用户性别：男" not in text
    assert "首选语言是Python" in text
    assert "## Facts" in text
    assert "## Preferences" in text
    assert "（暂无偏好记录）" in text


def test_pure_functional_equivalence_golden():
    """INV-MEM-01: Identical input records yield bit-identical output."""
    records = [
        _record(record_id="mem_1", content="偏好简洁", category=MemoryCategory.PREFERENCE, importance=0.9),
        _record(record_id="mem_2", content="运行在Linux", category=MemoryCategory.FACT, importance=0.8),
    ]
    out1 = render_curated_memory_markdown(records)
    out2 = render_curated_memory_markdown(records)
    assert out1 == out2
