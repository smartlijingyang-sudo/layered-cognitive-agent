# tests/reflect/test_memory_pre_filter_contract.py
from __future__ import annotations

from lca.contracts.protocols.memory.filter import FilterDecision, MemoryPreFilter


def test_filter_decision_structure():
    decision = FilterDecision(
        should_extract=True,
        reason="test",
        source="typesafe",
        confidence=0.95,
    )
    assert decision.should_extract is True
    assert decision.reason == "test"
    assert decision.source == "typesafe"
    assert decision.confidence == 0.95


def test_protocol_runtime_checkable():
    class DummyFilter:
        async def evaluate(self, text: str) -> FilterDecision:
            return FilterDecision(True, "dummy", "dummy", 1.0)

    assert isinstance(DummyFilter(), MemoryPreFilter)
