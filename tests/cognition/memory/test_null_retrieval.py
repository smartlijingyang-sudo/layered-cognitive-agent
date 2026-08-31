"""NullRetrievalPolicy —— ADR-0068 / 宪法 §3.4 默认 no-op。"""

import pytest

from lca.cognition.memory.null_retrieval_policy import NullRetrievalPolicy
from lca.contracts.atoms.enums import MemoryLayer
from lca.contracts.models.core.memory import MemoryRecord


@pytest.fixture()
def layers() -> dict[MemoryLayer, list[MemoryRecord]]:
    return {
        MemoryLayer.WORKING: [
            MemoryRecord(
                record_id="w1",
                content="working",
                memory_type=MemoryLayer.WORKING,
                importance=0.9,
            )
        ],
        MemoryLayer.SEMANTIC: [
            MemoryRecord(
                record_id="s1",
                content="semantic",
                memory_type=MemoryLayer.SEMANTIC,
                importance=0.8,
            )
        ],
        MemoryLayer.EPISODIC: [
            MemoryRecord(
                record_id="e1",
                content="episodic",
                memory_type=MemoryLayer.EPISODIC,
                importance=0.7,
            )
        ],
        MemoryLayer.PROCEDURAL: [
            MemoryRecord(
                record_id="p1",
                content="procedural",
                memory_type=MemoryLayer.PROCEDURAL,
                importance=0.6,
            )
        ],
    }


def test_null_retrieval_returns_empty(layers) -> None:
    policy = NullRetrievalPolicy()
    result = policy.retrieve(layers, budget=20)
    # Null 默认不返回任何记录
    assert result == []


def test_null_retrieval_ignores_budget(layers) -> None:
    policy = NullRetrievalPolicy()
    assert policy.retrieve(layers, budget=1) == []
    assert policy.retrieve(layers, budget=100) == []
