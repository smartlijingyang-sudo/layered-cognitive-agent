"""ADR-0169 D8 / PR-25:PersistenceCoordinator 测试。

验证 NullPersistenceCoordinator 满足 PersistenceCoordinator Protocol 契约:
- flush / close 是 no-op
- restore(from_seq) 返回空迭代器
- stats() 返回全 0 PersistenceStats

FilePersistenceCoordinator / CloseBarrier 协同行为在各自模块的 test_*.py 中。
"""

from __future__ import annotations

from lca.infrastructure.observability.loop_cursor.persistence_coordinator import (
    NullPersistenceCoordinator,
    PersistenceCoordinator,
    PersistenceStats,
)


def test_null_persistence_flush_and_close_are_noops() -> None:
    """``NullPersistenceCoordinator`` flush/close 不抛、不改状态(ADR-0169 D8)。"""
    coord = NullPersistenceCoordinator()
    assert coord.flush() is None
    assert coord.close() is None
    # 幂等:再次调用仍 no-op
    assert coord.flush() is None
    assert coord.close() is None


def test_null_persistence_restore_returns_empty_iterator() -> None:
    """``NullPersistenceCoordinator.restore(from_seq)`` 返回空迭代器(任意 from_seq)。"""
    coord = NullPersistenceCoordinator()
    assert list(coord.restore(from_seq=0)) == []
    assert list(coord.restore(from_seq=42)) == []


def test_null_persistence_stats_returns_zero_persistence_stats() -> None:
    """``NullPersistenceCoordinator.stats()`` 返回全 0 PersistenceStats;满足 Protocol。"""
    coord = NullPersistenceCoordinator()
    stats = coord.stats()
    assert isinstance(stats, PersistenceStats)
    assert stats.total_appended == 0
    assert stats.last_seq == 0
    assert stats.bytes_written == 0
    # 满足 PersistenceCoordinator Protocol(runtime_checkable)
    assert isinstance(coord, PersistenceCoordinator)
