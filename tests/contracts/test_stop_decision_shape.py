"""Pin the post-retirement StopDecision shape.

Locks in the contract after retiring the stop-decision half of the stop phase
(plan `docs/plans/2026-09-14-stop-decision-retirement.md`, PR-1). The boolean
`should_stop` field is gone; loop termination is a model-driven or
host-driven terminal payload built by `TerminalCommitExecutor` (PR-4) or
raised from Body as `DeterministicToolError` (PR-3). `StopReason.TASK_COMPLETED`
is gone because the model never produces it. ADR-0094 history is preserved
in the superseded note on the file but no longer encodes a runtime seam.
"""

from __future__ import annotations

from dataclasses import fields

from lca.contracts.models.core.policy.stop import StopDecision, StopReason


def test_stop_decision_has_no_should_stop_field() -> None:
    field_names = {f.name for f in fields(StopDecision)}
    assert "should_stop" not in field_names, (
        "should_stop is gone; loop termination is driven by "
        "decision.action_type, Body's DeterministicToolError, "
        "and the budget guard, not by a host policy."
    )


def test_stop_decision_keeps_terminal_payload() -> None:
    field_names = {f.name for f in fields(StopDecision)}
    assert field_names == {"reason", "final_output", "status", "failure"}, (
        "the four remaining fields are the SSOT for the reducer's "
        "apply_stop input."
    )


def test_stop_reason_drops_task_completed() -> None:
    members = {member.name for member in StopReason}
    assert members == {"CONTINUE", "BUDGET_EXCEEDED", "ERROR"}, (
        "TASK_COMPLETED is gone; the model never asserts task completion. "
        "The reason field on StopDecision is set by the model emitting "
        "RESPOND (via TerminalCommitExecutor), by Body's "
        "DeterministicToolError, or by the budget guard."
    )