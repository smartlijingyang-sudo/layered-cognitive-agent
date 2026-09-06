"""ActJournalReceipt commit tests (ADR-0194 P1-11)."""

from __future__ import annotations

from lca.contracts.models.core.policy.budget import Budget
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.models.observability.act.journal_receipt import (
    ActJournalReceipt,
    approval_requested_receipt,
    decision_made_receipt,
    synthesis_completed_receipt,
)
from lca.loop.commit.act_journal import commit_act_journal_receipt
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.session.append import Session


class _StubTool:
    name = "askUserQuestion"


def test_commit_decision_made_receipt() -> None:
    session = Session("t-act-decision-1")
    token = set_publish_session(session)
    try:
        state = AgentState(trace_id="trace-1", task="t", budget=Budget(), step=2)
        decision = Decision(
            decision_id="d1",
            action_type="respond",
            rationale="because",
            response_text="hello",
            confidence=0.9,
        )
        receipt = decision_made_receipt(decision, state)
        result = commit_act_journal_receipt(receipt)
        assert result is not None
        assert session.event_count == 1
        event = session.event_at(0)
        assert event is not None
        assert event.type == "decision.made.v1"
        assert event.data["step"] == 2
        assert event.data["response_text"] == "hello"
    finally:
        reset_publish_session(token)


def test_commit_act_journal_receipt_noop_when_unbound() -> None:
    from lca.contracts.models.observability.journal.journal import DecisionMade

    receipt = ActJournalReceipt(
        journal_event=DecisionMade(step=1, action_type="stop"),
    )
    assert commit_act_journal_receipt(receipt) is None


def test_commit_approval_requested_receipt() -> None:
    session = Session("t-act-approval-1")
    token = set_publish_session(session)
    try:
        receipt = approval_requested_receipt(_StubTool(), "inv-hil")  # type: ignore[arg-type]
        result = commit_act_journal_receipt(receipt)
        assert result is not None
        event = session.event_at(0)
        assert event is not None
        assert event.type == "approval.requested.v1"
        assert event.data["envelope_id"] == "inv-hil"
    finally:
        reset_publish_session(token)


def test_commit_synthesis_completed_receipt() -> None:
    session = Session("t-act-synthesis-1")
    token = set_publish_session(session)
    try:
        receipt = synthesis_completed_receipt(
            method="full",
            candidate_count=3,
            output_text="final answer",
        )
        result = commit_act_journal_receipt(receipt)
        assert result is not None
        event = session.event_at(0)
        assert event is not None
        assert event.type == "synthesis.completed.v1"
        assert event.data["output_text"] == "final answer"
    finally:
        reset_publish_session(token)
