"""Regression tests for the passive phase-observation state boundary."""

from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext
from dataclasses import FrozenInstanceError

import pytest

from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_phase_graph import (
    PhaseInput,
    PhaseResult,
    SemanticPhase,
)
from lca.contracts.protocols.journal.phase_observation import PhaseStateSnapshot
from lca.harness.declarative.compile.assembler import ExecutableNode
from lca.harness.declarative.graph.traversal import PhaseTraversal
from lca.harness.declarative.lifecycle.phase_observation import PhaseObserver, phase_state_snapshot
from lca.harness.declarative.lifecycle.phase_transaction import PhaseExecutionTransaction


class _Journal:
    def commit_fact(self, fact: object, *, plan_ref: str, node_ref: str) -> str:
        del fact, plan_ref
        return node_ref

    def commit_evidence(self, evidence_ref: str, *, plan_ref: str, node_ref: str) -> str:
        del plan_ref, node_ref
        return evidence_ref

    def commit_observation(
        self,
        observation: object,
        *,
        plan_ref: str,
        node_ref: str,
    ) -> str:
        del observation, plan_ref
        return node_ref


class _CapturingObserver(PhaseObserver):
    def __init__(self) -> None:
        self.observed: PhaseStateSnapshot | None = None

    def observe(
        self,
        *,
        semantic_phase: SemanticPhase,
        state: PhaseStateSnapshot,
    ) -> AbstractContextManager[object]:
        del semantic_phase
        self.observed = state
        return nullcontext()


class _PerceiveExecutor:
    async def execute(self, context: object, phase_input: PhaseInput) -> PhaseResult:
        del context, phase_input
        return PhaseResult(result_kind="context", payload="manifest")


def _state() -> AgentState:
    return AgentState(
        trace_id="trace-observation",
        task="do not expose this task to observers",
        budget=Budget(max_steps=7, used_steps=2, used_tokens=11),
        agent_role="researcher",
    )


def test_phase_state_snapshot_is_immutable_and_decoupled_from_live_state() -> None:
    state = _state()

    snapshot = phase_state_snapshot(state)
    state.step = 6
    state.budget.used_steps = 6
    state.working_memory["internal_marker"] = "changed-after-capture"

    assert snapshot.trace_id == "trace-observation"
    assert snapshot.agent_role == "researcher"
    assert snapshot.step == 0
    assert snapshot.budget.used_steps == 2
    assert snapshot.budget.used_tokens == 11
    assert not hasattr(snapshot, "task")
    assert not hasattr(snapshot, "working_memory")
    with pytest.raises(FrozenInstanceError):
        snapshot.step = 9
    with pytest.raises(FrozenInstanceError):
        snapshot.budget.used_steps = 9


def test_opaque_state_carrier_produces_anonymous_observation_snapshot() -> None:
    snapshot = phase_state_snapshot({"internal_marker": "not-observable"})

    assert snapshot.trace_id == ""
    assert snapshot.agent_role == ""
    assert snapshot.step == 0
    assert snapshot.budget.used_steps == 0
    assert not hasattr(snapshot, "working_memory")


@pytest.mark.asyncio
async def test_phase_transaction_passes_only_a_phase_state_snapshot_to_observer() -> None:
    observer = _CapturingObserver()
    transaction = PhaseExecutionTransaction(
        journal=_Journal(),
        effect_gateway=None,
        reducer=None,
        phase_observer=observer,
    )
    state = _state()
    traversal = PhaseTraversal.start(
        plan_ref="test-plan",
        entry_node_id="perceive.main",
        artifacts=None,
        input=None,
    )
    node = ExecutableNode(
        node_id="perceive.main",
        semantic_phase=SemanticPhase.PERCEIVE,
        executor_capability="phase.perceive.test",
        executor=_PerceiveExecutor(),
        contributions=(),
    )

    await transaction.run(
        node_id="perceive.main",
        semantic_phase=SemanticPhase.PERCEIVE,
        executable_node=node,
        state=state,
        budget=state.budget,
        plan_ref="test-plan",
        traversal=traversal,
        visit_count=1,
        capabilities=None,
        effect_policy=None,
    )

    assert observer.observed is not None
    assert observer.observed.trace_id == state.trace_id
    assert observer.observed.step == state.step
    assert observer.observed.budget.used_steps == state.budget.used_steps
    assert not hasattr(observer.observed, "working_memory")
