"""Tests for the harness-owned interpretation of typed control verdicts."""

from __future__ import annotations

import pytest

from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.models.core.stop import StopDecision, StopReason
from lca.contracts.protocols.gate.control_verdict import ControlVerdict, ControlVerdictKind
from lca.contracts.protocols.declarative.declarative_phase_graph import PhaseResult
from lca.harness.declarative.phase_context import RestrictedPhaseContext
from lca.harness.declarative.phase_governance import interpret_control_verdict
from lca.harness.declarative.traversal import PhaseTraversal


@pytest.mark.parametrize(
    ("kind", "fact_kind", "outcome_kind", "reason", "status"),
    [
        (ControlVerdictKind.ALLOW, None, None, None, None),
        (ControlVerdictKind.REWRITE, "control.rewrite_requested", None, None, None),
        (
            ControlVerdictKind.DENY,
            "control.denied",
            "failed",
            StopReason.ERROR,
            TaskStatus.FAILED,
        ),
        (
            ControlVerdictKind.EXHAUSTED,
            "control.exhausted",
            "failed",
            StopReason.BUDGET_EXCEEDED,
            TaskStatus.FAILED,
        ),
        (
            ControlVerdictKind.STOP,
            "control.stopped",
            "completed",
            StopReason.TASK_COMPLETED,
            TaskStatus.COMPLETED,
        ),
        (
            ControlVerdictKind.ASK_HUMAN,
            "control.paused",
            "paused",
            StopReason.CONTINUE,
            TaskStatus.INPUT_REQUIRED,
        ),
    ],
)
def test_interpret_control_verdict_centralizes_every_declared_meaning(
    kind: ControlVerdictKind,
    fact_kind: str | None,
    outcome_kind: str | None,
    reason: StopReason | None,
    status: TaskStatus | None,
) -> None:
    """Every typed verdict has explicit evidence and, when blocking, one outcome."""
    traversal = PhaseTraversal.start(
        plan_ref="plan:test",
        entry_node_id="think.main",
        artifacts=None,
        input=None,
    )
    result = PhaseResult(result_kind="decision", evidence_refs=("evidence:test",))
    state = AgentState(trace_id="trace:test", task="test", budget=Budget())

    interpretation = interpret_control_verdict(
        payload=ControlVerdict(
            plugin_id="control.test",
            kind=kind,
            detail="test detail",
        ),
        contribution="control.test",
        plan_ref="plan:test",
        node_id="think.main",
        result=result,
        traversal=traversal,
        state=state,
    )

    assert interpretation.verdict.kind is kind
    if fact_kind is None:
        assert interpretation.fact is None
    else:
        assert interpretation.fact is not None
        assert interpretation.fact.kind == fact_kind
        assert interpretation.fact.payload["detail"] == "test detail"

    if outcome_kind is None:
        assert interpretation.outcome is None
        return

    assert interpretation.outcome is not None
    assert interpretation.outcome.kind == outcome_kind
    assert interpretation.outcome.stop.reason is reason
    assert interpretation.outcome.stop.status is status
    assert interpretation.outcome.cursor.causation_refs == ("evidence:test",)


def test_stop_verdict_preserves_main_stop_output() -> None:
    """A later governance stop retains the output produced by the main STOP phase."""

    traversal = PhaseTraversal.start(
        plan_ref="plan:test",
        entry_node_id="stop.main",
        artifacts=None,
        input=None,
    )
    interpretation = interpret_control_verdict(
        payload=ControlVerdict(
            plugin_id="control.stop.focus",
            kind=ControlVerdictKind.STOP,
            detail="focus closure",
        ),
        contribution="control.stop.focus",
        plan_ref="plan:test",
        node_id="stop.main",
        result=PhaseResult(
            result_kind="stop_decision",
            payload=StopDecision(should_stop=False, final_output="partial delivery"),
        ),
        traversal=traversal,
        state=AgentState(trace_id="trace:test", task="test", budget=Budget()),
    )

    assert interpretation.outcome is not None
    assert interpretation.outcome.stop.final_output == "partial delivery"


def test_human_input_verdict_preserves_request_context() -> None:
    """A pause outcome exposes the contribution and detail needed by the caller."""
    traversal = PhaseTraversal.start(
        plan_ref="plan:test",
        entry_node_id="think.main",
        artifacts=None,
        input=None,
    )

    interpretation = interpret_control_verdict(
        payload=ControlVerdict(
            plugin_id="control.human",
            kind=ControlVerdictKind.ASK_HUMAN,
            detail="approval required",
        ),
        contribution="control.human",
        plan_ref="plan:test",
        node_id="think.main",
        result=PhaseResult(result_kind="decision"),
        traversal=traversal,
        state=AgentState(trace_id="trace:test", task="test", budget=Budget()),
    )

    assert interpretation.outcome is not None
    assert interpretation.outcome.approval_request == {
        "type": "control_paused",
        "contribution": "control.human",
        "verdict": "ask_human",
        "detail": "approval required",
    }


class _Journal:
    def __init__(self) -> None:
        self.facts: list[object] = []

    def commit_fact(self, fact: object, *, plan_ref: str, node_ref: str) -> str:
        del plan_ref, node_ref
        self.facts.append(fact)
        return "fact:test"

    def commit_evidence(self, evidence_ref: str, *, plan_ref: str, node_ref: str) -> str:
        del plan_ref, node_ref
        return evidence_ref

    def commit_observation(self, observation: object, *, plan_ref: str, node_ref: str) -> str:
        del plan_ref, node_ref
        return "observation:test"


class _GovernExecutor:
    def __init__(self, kind: ControlVerdictKind) -> None:
        self._kind = kind

    async def execute(self, _context: object, _input: object) -> PhaseResult:
        return PhaseResult(
            result_kind="control",
            payload=ControlVerdict(
                plugin_id="control.integration",
                kind=self._kind,
                detail="integration detail",
            ),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "expected_fact", "expected_outcome", "commits_immediately"),
    [
        (ControlVerdictKind.REWRITE, "control.rewrite_requested", None, False),
        (ControlVerdictKind.STOP, "control.stopped", "completed", True),
    ],
)
async def test_phase_governance_keeps_rewrite_nonblocking_and_stops_explicitly(
    kind: ControlVerdictKind,
    expected_fact: str,
    expected_outcome: str | None,
    commits_immediately: bool,
) -> None:
    """Governance owns verdict interpretation while the transaction owns later commits."""
    from lca.contracts.protocols.declarative.declarative_phase_graph import (
        ContributionRole,
        PhaseContribution,
        SemanticPhase,
    )
    from lca.harness.declarative.assembler import ExecutableContribution, ExecutableNode
    from lca.harness.declarative.phase_capabilities import MappingPhaseCapabilities
    from lca.harness.declarative.phase_context import RestrictedPhaseContext
    from lca.harness.declarative.phase_governance import PhaseGovernance

    journal = _Journal()
    state = AgentState(trace_id="trace:test", task="test", budget=Budget())
    context = RestrictedPhaseContext(
        plan_ref="plan:test",
        node_ref="think.main",
        state=state,
        journal=journal,
        budget=Budget(),
        artifacts={},
        capabilities=MappingPhaseCapabilities({}),
    )
    contribution = ExecutableContribution(
        declaration=PhaseContribution(
            phase=SemanticPhase.THINK,
            role=ContributionRole.GOVERN,
            executor="control.integration",
            output="control",
            aggregation="first-terminal",
        ),
        executor=_GovernExecutor(kind),
    )
    node = ExecutableNode(
        node_id="think.main",
        semantic_phase=SemanticPhase.THINK,
        executor_capability="phase.think.test",
        executor=_GovernExecutor(ControlVerdictKind.ALLOW),
        contributions=(contribution,),
    )
    traversal = PhaseTraversal.start(
        plan_ref="plan:test",
        entry_node_id="think.main",
        artifacts=None,
        input=None,
    )

    governed = await PhaseGovernance().apply(
        node,
        context,
        PhaseResult(result_kind="decision", payload="candidate"),
        plan_ref="plan:test",
        node_id="think.main",
        traversal=traversal,
    )

    assert governed.outcome is None or governed.outcome.kind == expected_outcome
    if commits_immediately:
        assert len(journal.facts) == 1
        assert journal.facts[0].kind == expected_fact
    else:
        assert journal.facts == []
        assert governed.result.facts[-1].kind == expected_fact


class _ContextCapturingGovernExecutor:
    def __init__(self) -> None:
        self.context: RestrictedPhaseContext | None = None

    async def execute(self, context: RestrictedPhaseContext, _input: object) -> PhaseResult:
        self.context = context
        return PhaseResult(
            result_kind="control",
            payload=ControlVerdict(
                plugin_id="control.context-capture",
                kind=ControlVerdictKind.ALLOW,
                detail="capture typed semantic context",
            ),
        )


@pytest.mark.asyncio
async def test_phase_governance_uses_semantic_phase_when_node_name_is_custom() -> None:
    """A renamed Think node still exposes its Decision to govern contributions."""
    from lca.contracts.models.core.decision import Decision
    from lca.contracts.protocols.declarative.declarative_phase_graph import (
        ContributionRole,
        PhaseContribution,
        SemanticPhase,
    )
    from lca.harness.declarative.assembler import ExecutableContribution, ExecutableNode
    from lca.harness.declarative.phase_capabilities import MappingPhaseCapabilities
    from lca.harness.declarative.phase_context import RestrictedPhaseContext
    from lca.harness.declarative.phase_governance import PhaseGovernance

    journal = _Journal()
    state = AgentState(trace_id="trace:test", task="test", budget=Budget())
    decision = Decision(
        decision_id="decision:test",
        action_type="respond",
        rationale="exercise semantic phase propagation",
        confidence=1.0,
    )
    context = RestrictedPhaseContext(
        plan_ref="plan:test",
        node_ref="strategy.primary-decision",
        state=state,
        journal=journal,
        budget=Budget(),
        artifacts={},
        capabilities=MappingPhaseCapabilities({}),
    )
    recorder = _ContextCapturingGovernExecutor()
    contribution = ExecutableContribution(
        declaration=PhaseContribution(
            phase=SemanticPhase.THINK,
            role=ContributionRole.GOVERN,
            executor="control.context-capture",
            output="control",
            aggregation="first-terminal",
        ),
        executor=recorder,
    )
    node = ExecutableNode(
        node_id="strategy.primary-decision",
        semantic_phase=SemanticPhase.THINK,
        executor_capability="phase.think.test",
        executor=_GovernExecutor(ControlVerdictKind.ALLOW),
        contributions=(contribution,),
    )
    traversal = PhaseTraversal.start(
        plan_ref="plan:test",
        entry_node_id="strategy.primary-decision",
        artifacts=None,
        input=None,
    )

    await PhaseGovernance().apply(
        node,
        context,
        PhaseResult(result_kind="decision", payload=decision),
        plan_ref="plan:test",
        node_id="strategy.primary-decision",
        traversal=traversal,
    )

    assert recorder.context is not None
    assert recorder.context.decision is decision
