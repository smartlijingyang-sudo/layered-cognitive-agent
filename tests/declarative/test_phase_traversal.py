"""Focused tests for declarative phase-graph traversal bookkeeping."""

from __future__ import annotations

import pytest

from lca.contracts.protocols.declarative.declarative_phase_graph import (
    DeclarativeValidationError,
    LoopGuard,
    PhaseEdge,
    PhaseInput,
    PhaseResult,
    SemanticPhase,
)
from lca.harness.declarative.graph.traversal import PhaseTraversal


def test_traversal_checkpoints_complete_execution_state() -> None:
    traversal = PhaseTraversal.start(
        plan_ref="plan-1",
        entry_node_id="think.main",
        artifacts={"task": "answer"},
        input=PhaseInput(artifact="question", causation_refs=("message-1",)),
    )

    assert traversal.visit(node_id="think.main", max_visits=2) == 1
    payload = traversal.record_result(
        semantic_phase=SemanticPhase.THINK,
        result=PhaseResult(result_kind="decision", payload={"choice": "respond"}),
        effect_output=None,
    )
    traversal.advance(
        edge=PhaseEdge(source="think.main", target="act.main", when="true"),
        payload=payload,
        causation_refs=("decision-1",),
    )

    cursor = traversal.checkpoint(causation_refs=("decision-1",), state_step=4)

    assert cursor.node_id == "act.main"
    assert cursor.visit_counts == (("think.main", 1),)
    assert cursor.edge_counts == (("think.main", "act.main", 1),)
    assert cursor.artifacts["think"] == {"choice": "respond"}
    assert cursor.causation_refs == ("decision-1",)
    assert cursor.budget_snapshot == {"step": 4}


def test_resumed_traversal_uses_persisted_payload_when_no_input_is_supplied() -> None:
    original = PhaseTraversal.start(
        plan_ref="plan-1",
        entry_node_id="perceive.main",
        artifacts=None,
        input=None,
    )
    original.record_result(
        semantic_phase=SemanticPhase.PERCEIVE,
        result=PhaseResult(result_kind="perception", payload="observed"),
        effect_output=None,
    )
    cursor = original.checkpoint(node_id="think.main", causation_refs=("fact-1",))

    resumed = PhaseTraversal.resume(cursor=cursor, input=None)

    assert resumed.current_node_id == "think.main"
    assert resumed.next_input.artifact == "observed"
    assert resumed.next_input.causation_refs == ("fact-1",)


def test_traversal_rejects_loop_budget_exhaustion() -> None:
    traversal = PhaseTraversal.start(
        plan_ref="plan-1",
        entry_node_id="reflect.main",
        artifacts=None,
        input=None,
    )
    edge = PhaseEdge(
        source="reflect.main",
        target="think.main",
        when="true",
        loop=LoopGuard(max_iterations=1, budget="recovery", terminal_predicate="false"),
    )

    traversal.advance(edge=edge, payload=None, causation_refs=())

    with pytest.raises(DeclarativeValidationError, match="loop edge budget exhausted"):
        traversal.advance(edge=edge, payload=None, causation_refs=())


def test_reset_visit_preserves_other_durable_bookkeeping() -> None:
    traversal = PhaseTraversal.start(
        plan_ref="plan-1",
        entry_node_id="think.main",
        artifacts=None,
        input=None,
    )
    traversal.visit(node_id="think.main", max_visits=2)
    traversal.visit(node_id="act.main", max_visits=2)

    traversal.reset_visit("think.main")
    cursor = traversal.checkpoint(node_id="think.main")

    assert cursor.visit_counts == (("act.main", 1),)
