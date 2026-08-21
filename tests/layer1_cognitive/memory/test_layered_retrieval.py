"""LayeredRetrievalPolicy —— ADR-0068 / v3 §8 4 层加权 retrieval。"""

import pytest

from lca.contracts.atoms.enums import MemoryLayer
from lca.contracts.models.core.memory import MemoryRecord
from lca.layer1_cognitive.memory.layered_retrieval_policy import (
    LayeredRetrievalPolicy,
)


def _rec(layer: MemoryLayer, record_id: str, recency: float) -> MemoryRecord:
    return MemoryRecord(
        record_id=record_id,
        content=f"{record_id}",
        memory_type=layer,
        importance=recency,
        recency_score=recency,
    )


@pytest.fixture()
def layers() -> dict[MemoryLayer, list[MemoryRecord]]:
    return {
        MemoryLayer.WORKING: [_rec(MemoryLayer.WORKING, f"w{i}", 0.5) for i in range(3)],
        MemoryLayer.SEMANTIC: [
            _rec(MemoryLayer.SEMANTIC, f"s{i}", 0.4 + i * 0.1) for i in range(4)
        ],
        MemoryLayer.EPISODIC: [
            _rec(MemoryLayer.EPISODIC, f"e{i}", 0.3 + i * 0.1) for i in range(3)
        ],
        MemoryLayer.PROCEDURAL: [
            _rec(MemoryLayer.PROCEDURAL, f"p{i}", 0.2 + i * 0.1) for i in range(2)
        ],
    }


def test_working_preserved_unconditionally(layers) -> None:
    """Working 永保留，不占 budget。"""
    policy = LayeredRetrievalPolicy()
    result = policy.retrieve(layers, budget=0)
    assert len(result) == 0  # budget=0 时 working 也被 cap 到 0


def test_working_exceeds_budget(layers) -> None:
    """Working 超 budget 时，只保留前 budget 个。"""
    policy = LayeredRetrievalPolicy()
    result = policy.retrieve(layers, budget=2)
    assert len(result) == 2
    assert all(r.memory_type == MemoryLayer.WORKING for r in result)


def test_semantic_procedural_prioritized_over_episodic(layers) -> None:
    """SEMANTIC + PROCEDURAL 共享 70% budget，EPISODIC 只占 30%。"""
    policy = LayeredRetrievalPolicy()
    result = policy.retrieve(layers, budget=10)
    # Working 3 个保留（不占 budget）；剩 7 个 budget
    # SP budget = int(7 * 0.7) = 4
    # EP budget = 7 - 4 = 3
    working_count = sum(1 for r in result if r.memory_type == MemoryLayer.WORKING)
    sp_count = sum(
        1 for r in result if r.memory_type in (MemoryLayer.SEMANTIC, MemoryLayer.PROCEDURAL)
    )
    ep_count = sum(1 for r in result if r.memory_type == MemoryLayer.EPISODIC)
    assert working_count == 3
    assert sp_count <= 4
    assert ep_count <= 3


def test_top_by_recency_descending(layers) -> None:
    """按 recency_score 降序挑选。"""
    policy = LayeredRetrievalPolicy()
    result = policy.retrieve(layers, budget=20)
    sp_records = [
        r for r in result if r.memory_type in (MemoryLayer.SEMANTIC, MemoryLayer.PROCEDURAL)
    ]
    # Semantic 有 s3 (recency=0.7), s2 (0.6), s1 (0.5), s0 (0.4)
    # Procedural 有 p1 (0.3), p0 (0.2)
    # Top 4 by recency: s3, s2, s1, p1
    sp_ids = [r.record_id for r in sp_records]
    assert "s3" in sp_ids
    assert "s2" in sp_ids
    assert "s1" in sp_ids
    # p1 (0.3) > s0 (0.4) 但 s0 不在 top 4，所以 p1 入选


def test_empty_layers(layers) -> None:
    """空 layers 返回空列表。"""
    policy = LayeredRetrievalPolicy()
    result = policy.retrieve({}, budget=10)
    assert result == []
