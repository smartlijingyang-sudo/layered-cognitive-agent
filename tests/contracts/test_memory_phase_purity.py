"""ADR-0249: consolidation is not a semantic phase."""

from __future__ import annotations

from lca.contracts.protocols.declarative.declarative_1.declarative_common import SemanticPhase


def test_semantic_phase_order_excludes_consolidation() -> None:
    assert tuple(phase.value for phase in SemanticPhase) == (
        "perceive",
        "think",
        "act",
        "reflect",
        "remember",
        "stop",
    )
    assert "consolidation" not in {phase.value for phase in SemanticPhase}
