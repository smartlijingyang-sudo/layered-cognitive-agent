"""PR-1（ADR-0246）：``MemoryRecord`` schema 契约测试。

验证新增 ``category`` / ``dedupe_key`` 字段的默认值兼容性与非法输入拒绝。
"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord


def test_memory_record_requires_category_on_construction() -> None:
    """显式提供 ``category`` 时记录合法。"""
    record = MemoryRecord(
        record_id="mem_1",
        content="用户身份：架构师",
        memory_type=MemoryLayer.SEMANTIC,
        importance=0.9,
        category=MemoryCategory.IDENTITY,
        dedupe_key="identity:architect",
    )
    assert record.category is MemoryCategory.IDENTITY
    assert record.dedupe_key == "identity:architect"


def test_memory_record_old_construction_gets_defaults() -> None:
    """旧调用不传新字段时使用默认值（序列化兼容）。"""
    record = MemoryRecord(
        record_id="mem_old",
        content="legacy content",
        memory_type=MemoryLayer.SEMANTIC,
        importance=0.5,
    )
    assert record.category is MemoryCategory.FACT
    assert record.dedupe_key is None


def test_memory_record_category_must_be_memory_category() -> None:
    """非法 ``category`` 值被拒绝。"""
    with pytest.raises(ValueError):
        MemoryRecord(
            record_id="mem_bad",
            content="x",
            memory_type=MemoryLayer.SEMANTIC,
            importance=0.5,
            category="not-a-category",  # type: ignore[arg-type]
        )


def test_memory_record_importance_still_validated() -> None:
    """既有重要性校验不被破坏。"""
    with pytest.raises(ValueError):
        MemoryRecord(
            record_id="mem_bad_importance",
            content="x",
            memory_type=MemoryLayer.SEMANTIC,
            importance=1.5,
        )
