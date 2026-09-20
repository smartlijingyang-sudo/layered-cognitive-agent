"""PR-4（ADR-0246）：检索策略预算/排除语义测试。"""

from __future__ import annotations

from lca.cognition.memory.layered.retrieval_policy import (
    LayeredRetrievalPolicy,
    estimate_tokens,
)
from lca.contracts.atoms.enums.enums import MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord


def _rec(
    record_id: str,
    content: str,
    *,
    layer: MemoryLayer = MemoryLayer.SEMANTIC,
    importance: float = 0.8,
    recency: float | None = 0.5,
    deleted: bool = False,
    valid_until_ms: int | None = None,
) -> MemoryRecord:
    return MemoryRecord(
        record_id=record_id,
        content=content,
        memory_type=layer,
        importance=importance,
        recency_score=recency,
        deleted=deleted,
        valid_until_ms=valid_until_ms,
    )


def _layers(records: list[MemoryRecord]) -> dict[MemoryLayer, list[MemoryRecord]]:
    return {MemoryLayer.SEMANTIC: records}


def test_estimate_tokens_character_approximation() -> None:
    assert estimate_tokens("") == 1
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcdefgh") == 2


def test_token_budget_truncates_selected_records() -> None:
    records = [_rec(f"mem_{i}", "内容" * 20, importance=0.9 - i * 0.1) for i in range(5)]
    policy = LayeredRetrievalPolicy()
    result = policy.retrieve(_layers(records), budget=10, token_budget=20)
    used = sum(estimate_tokens(r.content) for r in result)
    assert used <= 20
    assert len(result) < len(records)


def test_superseded_records_excluded() -> None:
    records = [
        _rec("old", "旧事实", deleted=True),
        _rec("active", "活跃事实", deleted=False),
    ]
    policy = LayeredRetrievalPolicy()
    result = policy.retrieve(_layers(records), budget=10)
    ids = [r.record_id for r in result]
    assert "active" in ids
    assert "old" not in ids


def test_expired_records_excluded() -> None:
    records = [
        _rec("expired", "过期事实", valid_until_ms=1),
        _rec("current", "当前事实", valid_until_ms=None),
    ]
    policy = LayeredRetrievalPolicy()
    result = policy.retrieve(_layers(records), budget=10)
    ids = [r.record_id for r in result]
    assert "current" in ids
    assert "expired" not in ids


def test_token_budget_none_returns_all_within_budget() -> None:
    records = [_rec(f"mem_{i}", "内容" * 10) for i in range(3)]
    policy = LayeredRetrievalPolicy()
    result = policy.retrieve(_layers(records), budget=10, token_budget=None)
    assert len(result) == 3
