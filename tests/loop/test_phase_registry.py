"""Unit tests for loop phase registry read model (ADR-0194 P4-L03)."""

from __future__ import annotations

from lca.contracts.protocols.declarative.declarative_1.declarative_common import SemanticPhase
from lca.loop.phases.registry import (
    PHASE_EXECUTOR_CAPABILITY_PREFIX,
    SEMANTIC_PHASE_ORDER,
    PhaseExecutorRegistry,
    is_semantic_phase_closed_set,
    phase_executor_capability_key,
    semantic_phases,
)


def test_semantic_phase_order_matches_closed_set() -> None:
    assert semantic_phases() == SEMANTIC_PHASE_ORDER
    assert is_semantic_phase_closed_set(SEMANTIC_PHASE_ORDER)
    assert not is_semantic_phase_closed_set(tuple(SEMANTIC_PHASE_ORDER[:-1]))


def test_phase_executor_capability_key_shape() -> None:
    assert (
        phase_executor_capability_key(semantic_phase=SemanticPhase.THINK, variant="standard")
        == "phase.think.standard"
    )
    assert PHASE_EXECUTOR_CAPABILITY_PREFIX == "phase."


def test_phase_executor_registry_groups_by_semantic_phase() -> None:
    sentinel = object()
    registry = PhaseExecutorRegistry(
        {
            "phase.think.standard": sentinel,  # type: ignore[arg-type]
            "phase.act.standard": object(),  # type: ignore[arg-type]
        }
    )
    think_bindings = registry.for_semantic_phase(SemanticPhase.THINK)
    assert think_bindings == (("phase.think.standard", sentinel),)
    assert registry.get("phase.think.standard") is sentinel
