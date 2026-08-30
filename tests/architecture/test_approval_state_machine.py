"""Architecture tests for replayable HIL approval transitions."""

from __future__ import annotations

import pytest

from lca.harness.declarative.approval import ApprovalState, ApprovalStateMachine


def test_approval_state_machine_replays_wait_and_resolution() -> None:
    machine = ApprovalStateMachine()
    events = [
        machine.apply("approval.requested", "approval-1", payload={"tool": "write"}),
        machine.apply("approval.waiting_input", "approval-1"),
        machine.apply("approval.resolved.approved", "approval-1"),
        machine.apply("approval.resumed", "approval-1"),
        machine.apply("effect.completed", "approval-1"),
    ]

    replayed = ApprovalStateMachine.replay(
        {
            "event": event.event,
            "approval_id": event.approval_id,
            "sequence": event.sequence,
            "payload": dict(event.payload),
        }
        for event in events
    )

    assert replayed.state("approval-1") is ApprovalState.EFFECT_COMPLETED


def test_approval_state_machine_rejects_resume_before_approval() -> None:
    machine = ApprovalStateMachine()
    machine.apply("approval.requested", "approval-1")
    machine.apply("approval.waiting_input", "approval-1")

    with pytest.raises(ValueError, match="invalid approval transition"):
        machine.apply("approval.resumed", "approval-1")


def test_approval_state_machine_rejects_duplicate_resolution() -> None:
    machine = ApprovalStateMachine()
    machine.apply("approval.requested", "approval-1")
    machine.apply("approval.waiting_input", "approval-1")
    machine.apply("approval.resolved.denied", "approval-1")

    with pytest.raises(ValueError, match="invalid approval transition"):
        machine.apply("approval.resolved.approved", "approval-1")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("event", "", "non-empty event"),
        ("approval_id", "", "non-empty approval_id"),
        ("sequence", "3", "sequence must be an integer"),
        ("sequence", True, "sequence must be an integer"),
    ],
)
def test_replay_rejects_coerced_journal_fact_types(field: str, value: object, message: str) -> None:
    event = {
        "event": "approval.requested",
        "approval_id": "approval-1",
        "sequence": 1,
    }
    event[field] = value

    with pytest.raises(ValueError, match=message):
        ApprovalStateMachine.replay([event])


@pytest.mark.parametrize(
    ("event", "approval_id", "message"),
    [
        (None, "approval-1", "approval event must be a non-empty string"),
        ("approval.requested", 7, "approval_id must be a non-empty string"),
    ],
)
def test_apply_rejects_untyped_approval_facts(
    event: object, approval_id: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        ApprovalStateMachine().apply(event, approval_id)  # type: ignore[arg-type]
