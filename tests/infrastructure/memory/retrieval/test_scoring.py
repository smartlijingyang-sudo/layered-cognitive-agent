"""Tests for the shared memory retrieval scoring seam.

These drive the real functions shipped in
``lca/infrastructure/memory/retrieval/scoring.py``, which both
``LayeredRetrievalPolicy`` and ``AssistantMemory.retrieve`` depend on.
"""

from __future__ import annotations

from lca.contracts.atoms.enums.enums import MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.infrastructure.memory.retrieval.scoring import (
    apply_token_budget,
    estimate_tokens,
    is_expired,
    relevance,
    score_record,
    select_top,
)


def _rec(
    record_id: str,
    content: str,
    *,
    importance: float = 0.8,
    recency_score: float | None = None,
    created_at_ms: int | None = None,
    deleted: bool = False,
    valid_until_ms: int | None = None,
) -> MemoryRecord:
    return MemoryRecord(
        record_id=record_id,
        content=content,
        memory_type=MemoryLayer.SEMANTIC,
        importance=importance,
        recency_score=recency_score,
        created_at_ms=created_at_ms,
        deleted=deleted,
        valid_until_ms=valid_until_ms,
    )


def test_estimate_tokens_floor_is_one() -> None:
    assert estimate_tokens("") == 1
    assert estimate_tokens("a") == 1


def test_estimate_tokens_approx_four_chars_per_token() -> None:
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcdefgh") == 2


def test_relevance_empty_query_is_neutral() -> None:
    assert relevance("", "任何内容") == 1.0


def test_relevance_chinese_overlap() -> None:
    # 中文按字符集合重叠：query 与 content 共享字符越多越相关。
    assert relevance("Redis 缓存配置与端口", "Redis 生产缓存集群端口为 6379") > relevance(
        "Redis 缓存配置与端口", "Kubernetes 部署命名空间"
    )


def test_relevance_english_overlap() -> None:
    assert relevance("redis cache port", "redis cluster") > relevance(
        "redis cache port", "kubernetes namespace"
    )


def test_relevance_substring_bonus() -> None:
    assert relevance("redis", "redis production cluster") > 1.0


def test_is_expired_never_expires_without_validity() -> None:
    record = _rec("r1", "内容", valid_until_ms=None)
    assert is_expired(record) is False


def test_is_expired_respects_valid_until() -> None:
    expired = _rec("r1", "内容", valid_until_ms=100)
    assert is_expired(expired, now_ms=200) is True
    fresh = _rec("r2", "内容", valid_until_ms=200)
    assert is_expired(fresh, now_ms=200) is False


def test_score_record_uses_recency_score_when_present() -> None:
    record = _rec("r1", "内容", importance=0.8, recency_score=0.9)
    assert score_record(record, "", now_ms=0) == 0.9 * 0.8


def test_score_record_ages_by_created_at_when_no_recency_score() -> None:
    record = _rec("r1", "内容", importance=0.8, created_at_ms=1000)
    # now_ms=1h later: age_hours=1 -> recency = max(0.2, 1/1.05) ≈ 0.952
    score = score_record(record, "", now_ms=1000 + 3600_000)
    assert 0.7 <= score <= 0.8
    # Much older record gets a lower recency (but floored at 0.2).
    old = _rec("r2", "内容", importance=0.8, created_at_ms=1000)
    old_score = score_record(old, "", now_ms=1000 + 100 * 3600_000)
    assert old_score < score


def test_score_record_defaults_without_any_recency() -> None:
    record = _rec("r1", "内容", importance=0.8)
    assert score_record(record, "", now_ms=None) == 0.8 * 0.5


def test_score_record_relevance_weights() -> None:
    record = _rec("r1", "redis cluster 缓存配置", importance=0.8, recency_score=0.5)
    matching = score_record(record, "redis 缓存", now_ms=0)
    unrelated = score_record(record, "kubernetes", now_ms=0)
    assert matching > unrelated


def test_select_top_excludes_deleted_and_expired() -> None:
    records = [
        _rec("r1", "alive", deleted=False),
        _rec("r2", "deleted", deleted=True),
        _rec("r3", "expired", valid_until_ms=100),
    ]
    top = select_top(records, 10, now_ms=200)
    assert [r.record_id for r in top] == ["r1"]


def test_select_top_deterministic_order() -> None:
    records = [
        _rec("r1", "a", importance=0.3, recency_score=0.3),
        _rec("r2", "b", importance=0.9, recency_score=0.9),
        _rec("r3", "c", importance=0.6, recency_score=0.6),
    ]
    first = select_top(records, 10)
    second = select_top(records, 10)
    assert [r.record_id for r in first] == [r.record_id for r in second]
    assert first[0].record_id == "r2"


def test_select_top_respects_budget() -> None:
    records = [_rec(f"r{i}", f"content {i}", importance=0.5, recency_score=0.5) for i in range(5)]
    top = select_top(records, 2)
    assert len(top) == 2


def test_select_top_empty_and_zero_budget() -> None:
    assert select_top([], 10) == []
    records = [_rec("r1", "a", importance=0.5, recency_score=0.5)]
    assert select_top(records, 0) == []


def test_apply_token_budget_none_returns_all() -> None:
    records = [_rec(f"r{i}", "x" * 20, importance=0.5, recency_score=0.5) for i in range(3)]
    assert apply_token_budget(records, token_budget=None) == records


def test_apply_token_budget_truncates() -> None:
    records = [_rec(f"r{i}", "x" * 8, importance=0.5, recency_score=0.5) for i in range(3)]
    # Each record ≈ 2 tokens; budget 5 keeps the first two, drops the third.
    kept = apply_token_budget(records, token_budget=5)
    assert [r.record_id for r in kept] == ["r0", "r1"]


def test_apply_token_budget_zero_returns_all() -> None:
    records = [_rec("r1", "x", importance=0.5, recency_score=0.5)]
    assert apply_token_budget(records, token_budget=0) == records
