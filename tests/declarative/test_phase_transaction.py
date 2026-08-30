"""Focused tests for one declarative phase execution transaction."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.protocols.act.command_envelope import RunDelta, RunFact
from lca.contracts.protocols.declarative.declarative_phase_graph import (
    DeclarativeValidationError,
    PhaseInput,
    PhaseResult,
    SemanticPhase,
)
from lca.contracts.protocols.journal.phase_observation import PhaseStateSnapshot
from lca.harness.declarative.compile.assembler import ExecutableNode
from lca.harness.declarative.compile.phase_capabilities import normalize_phase_capabilities
from lca.harness.declarative.lifecycle.phase_observation import NullPhaseObserver
from lca.harness.declarative.lifecycle.phase_transaction import PhaseExecutionTransaction
from lca.harness.declarative.graph.traversal import PhaseTraversal


@dataclass
class _Journal:
    facts: list[RunFact] = field(default_factory=list)
    observations: list[object] = field(default_factory=list)

    def commit_fact(self, fact: RunFact, *, plan_ref: str, node_ref: str) -> str:
        self.facts.append(fact)
        return fact.fact_id

    def commit_evidence(self, evidence_ref: str, *, plan_ref: str, node_ref: str) -> str:
        return evidence_ref

    def commit_observation(self, observation: object, *, plan_ref: str, node_ref: str) -> str:
        self.observations.append(observation)
        return f"{node_ref}:observation:{len(self.observations)}"


class _OpaqueCapabilities:
    pass


def test_phase_capabilities_reject_arbitrary_objects() -> None:
    """Phases receive a narrow reader, never an object inspected through getattr."""
    with pytest.raises(TypeError, match="PhaseCapabilityReader"):
        normalize_phase_capabilities(_OpaqueCapabilities())


class _RecordingDeltaReducer:
    def __init__(self) -> None:
        self.calls: list[RunDelta] = []

    def apply_delta(self, state: AgentState, delta: RunDelta) -> AgentState:
        self.calls.append(delta)
        return state


class _FoldOnlyReducer:
    def fold(self, state: AgentState, _delta: RunDelta) -> AgentState:
        return state


class _PerceiveExecutor:
    async def execute(self, _context: object, _input: PhaseInput) -> PhaseResult:
        return PhaseResult(
            result_kind="context",
            payload="manifest",
            facts=(RunFact(fact_id="source-fact", plan_ref="test-plan", kind="perception.ready"),),
        )


def test_transaction_applies_deltas_only_through_delta_reducer() -> None:
    """The transaction calls its declared seam without reducer method discovery."""
    reducer = _RecordingDeltaReducer()
    transaction = PhaseExecutionTransaction(
        journal=_Journal(),
        effect_gateway=None,
        reducer=reducer,
        phase_observer=NullPhaseObserver(),
    )
    state = AgentState(trace_id="trace", task="task", budget=Budget())
    delta = RunDelta(plan_ref="test-plan", metadata={"operation": "step"})

    assert transaction.apply_delta(state, delta) is state
    assert reducer.calls == [delta]


def test_transaction_rejects_fold_only_reducer() -> None:
    """Legacy fold-shaped objects must use an explicit DeltaReducer adapter."""
    transaction = PhaseExecutionTransaction(
        journal=_Journal(),
        effect_gateway=None,
        reducer=_FoldOnlyReducer(),
        phase_observer=NullPhaseObserver(),
    )
    state = AgentState(trace_id="trace", task="task", budget=Budget())
    delta = RunDelta(plan_ref="test-plan", metadata={"operation": "step"})

    with pytest.raises(DeclarativeValidationError, match=r"DeltaReducer\.apply_delta") as exc_info:
        transaction.apply_delta(state, delta)

    assert exc_info.value.code == "RT-001"


@pytest.mark.asyncio
async def test_phase_transaction_commits_audit_facts_and_next_artifact() -> None:
    """One node visit owns its phase fact, emitted facts, and next-phase artifact."""
    journal = _Journal()
    transaction = PhaseExecutionTransaction(
        journal=journal,
        effect_gateway=None,
        reducer=None,
        phase_observer=NullPhaseObserver(),
    )
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
    state = AgentState(trace_id="trace", task="task", budget=Budget())

    result = await transaction.run(
        node_id="perceive.main",
        semantic_phase=SemanticPhase.PERCEIVE,
        executable_node=node,
        state=state,
        budget=Budget(),
        plan_ref="test-plan",
        traversal=traversal,
        visit_count=1,
        capabilities=None,
        effect_policy=None,
    )

    assert result.state is state
    assert result.effective_payload == "manifest"
    assert [fact.kind for fact in result.facts] == ["phase.result", "perception.ready"]
    assert [fact.kind for fact in journal.facts] == ["phase.result", "perception.ready"]
    assert traversal.artifacts["perceive"] == "manifest"


class _RecordingObserver:
    def __init__(self) -> None:
        self.phases: list[SemanticPhase] = []

    def observe(self, *, semantic_phase: SemanticPhase, state: PhaseStateSnapshot):
        from contextlib import nullcontext

        del state
        self.phases.append(semantic_phase)
        return nullcontext()


@pytest.mark.asyncio
async def test_phase_transaction_observes_through_injected_adapter() -> None:
    """A driver may replace phase tracing without changing transaction behavior."""
    journal = _Journal()
    observer = _RecordingObserver()
    transaction = PhaseExecutionTransaction(
        journal=journal,
        effect_gateway=None,
        reducer=None,
        phase_observer=observer,
    )
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
        state=AgentState(trace_id="trace", task="task", budget=Budget()),
        budget=Budget(),
        plan_ref="test-plan",
        traversal=traversal,
        visit_count=1,
        capabilities=None,
        effect_policy=None,
    )

    assert observer.phases == [SemanticPhase.PERCEIVE]
