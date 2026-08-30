from __future__ import annotations

from dataclasses import dataclass, field

from lca.contracts.models.core.result import ApprovalPendingError
from lca.contracts.protocols.command_envelope import RunFact
from lca.harness.declarative.outcome_projection import RunOutcomeProjector
from lca.harness.declarative.traversal import PhaseTraversal


@dataclass
class _Journal:
    facts: list[RunFact] = field(default_factory=list)

    def commit_fact(self, fact: RunFact, *, plan_ref: str, node_ref: str) -> str:
        self.facts.append(fact)
        return fact.fact_id

    def commit_evidence(self, evidence_ref: str, *, plan_ref: str, node_ref: str) -> str:
        return evidence_ref

    def commit_observation(self, observation: object, *, plan_ref: str, node_ref: str) -> str:
        return node_ref


def _traversal() -> PhaseTraversal:
    return PhaseTraversal.start(
        plan_ref="plan-1",
        entry_node_id="act.main",
        artifacts={"think": "stale context", "perceive": "fresh context"},
        input=None,
    )


def test_pause_projection_commits_replayable_facts_and_declared_resume_cursor() -> None:
    journal = _Journal()
    traversal = _traversal()

    result = RunOutcomeProjector(journal).approval_pending(
        ApprovalPendingError({"approval_id": "approval-1", "tool": "write"}),
        traversal=traversal,
        state={"immutable": True},
        current_node_id="act.main",
        plan_ref="plan-1",
        visits=[],
        facts=[],
        approval_resume_node="think.after-approval",
    )

    assert result.outcome is not None
    assert result.outcome.kind == "paused"
    assert result.cursor is not None and result.cursor.node_id == "think.after-approval"
    assert result.outcome.approval_request == {"approval_id": "approval-1", "tool": "write"}
    assert "think" not in traversal.artifacts
    assert [fact.kind for fact in result.facts] == [
        "approval.requested",
        "approval.waiting_input",
        "run.paused",
    ]
    assert tuple(journal.facts) == result.facts
    assert result.facts[1].payload["payload"] == {"from_node": "act.main"}


def test_pause_projection_fails_closed_without_a_plan_declared_resume_node() -> None:
    journal = _Journal()
    traversal = _traversal()

    result = RunOutcomeProjector(journal).approval_pending(
        ApprovalPendingError({"tool": "write"}),
        traversal=traversal,
        state={"immutable": True},
        current_node_id="act.main",
        plan_ref="plan-1",
        visits=[],
        facts=[],
        approval_resume_node=None,
    )

    assert result.outcome is not None
    assert result.outcome.kind == "failed"
    assert result.outcome.error_fact is not None
    assert result.outcome.error_fact.payload["error_code"] == "PG-008"
    assert result.cursor is not None and result.cursor.node_id == "act.main"
    assert [fact.kind for fact in journal.facts] == ["run.failed"]
