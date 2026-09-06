"""ActJournalReceipt commit tests (ADR-0194 P1-11)."""

from __future__ import annotations

from lca.contracts.models.core.budget import Budget
from lca.contracts.models.core.decision import Decision
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.observability.act_journal_receipt import (
    ActJournalReceipt,
    approval_requested_receipt,
    decision_made_receipt,
    synthesis_completed_receipt,
)
from lca.contracts.models.observability.journal import ApprovalRequested, DecisionMade
from lca.loop.act_journal_commit import commit_act_journal_receipt


class _StubTool:
    name = "askUserQuestion"


def test_commit_decision_made_receipt() -> None:
    from lca.contracts.models.observability.journal import RunScope
    from lca.infrastructure.observability import bind_backends, run_scope
    from tests.support.observability_helpers import make_test_bound

    hub = make_test_bound()
    state = AgentState(trace_id="trace-1", task="t", budget=Budget(), step=2)
    decision = Decision(
        decision_id="d1",
        action_type="respond",
        rationale="because",
        response_text="hello",
        confidence=0.9,
    )
    receipt = decision_made_receipt(decision, state)
    with bind_backends(hub), run_scope(RunScope(trace_id="t1", run_id="r1")):
        stamped = commit_act_journal_receipt(receipt)
    assert stamped is not None
    assert isinstance(stamped.event, DecisionMade)
    assert stamped.event.step == 2
    assert stamped.event.response_text == "hello"


def test_commit_act_journal_receipt_noop_when_unbound() -> None:
    receipt = ActJournalReceipt(
        journal_event=DecisionMade(step=1, action_type="stop"),
    )
    assert commit_act_journal_receipt(receipt) is None


def test_commit_approval_requested_receipt() -> None:
    from lca.contracts.models.observability.journal import RunScope
    from lca.infrastructure.observability import bind_backends, run_scope
    from tests.support.observability_helpers import make_test_bound

    hub = make_test_bound()
    receipt = approval_requested_receipt(_StubTool(), "inv-hil")  # type: ignore[arg-type]
    with bind_backends(hub), run_scope(RunScope(trace_id="t1", run_id="r1")):
        stamped = commit_act_journal_receipt(receipt)
    assert stamped is not None
    assert isinstance(stamped.event, ApprovalRequested)
    assert stamped.event.envelope_id == "inv-hil"


def test_commit_synthesis_completed_receipt() -> None:
    from lca.contracts.models.observability.journal import RunScope, SynthesisCompleted
    from lca.infrastructure.observability import bind_backends, run_scope
    from tests.support.observability_helpers import make_test_bound

    hub = make_test_bound()
    receipt = synthesis_completed_receipt(
        method="full",
        candidate_count=3,
        output_text="final answer",
    )
    with bind_backends(hub), run_scope(RunScope(trace_id="t1", run_id="r1")):
        stamped = commit_act_journal_receipt(receipt)
    assert stamped is not None
    assert isinstance(stamped.event, SynthesisCompleted)
    assert stamped.event.output_text == "final answer"
