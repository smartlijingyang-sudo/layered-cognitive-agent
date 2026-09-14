"""Pin the new terminal spine EPs after retiring the stop-decision half.

Locks in the contract after retiring the stop-decision half of the stop phase
(plan `docs/plans/2026-09-14-stop-decision-retirement.md`, PR-2):

- `spine.terminal.commit` is the carrier for `TerminalCommitExecutor`. The
  fold reads `outcome` and `reason` to set `terminal_outcome`.
- `spine.body.deterministic_fail` is the carrier for Body's
  `DeterministicToolError` raise. The fold reads the EP and stamps
  `terminal_outcome="failed"`.

The session catalog admits these EPs via the merged `SPINE_EXECUTION_POINTS`
set; this test pins the catalog membership and the fold's outcome mapping.
"""

from __future__ import annotations

from lca_kernel.events.payloads.spine import SPINE_EVENT_CATEGORIES, SPINE_EXECUTION_POINTS


def test_terminal_commit_in_execution_points() -> None:
    assert "terminal.commit" in SPINE_EXECUTION_POINTS


def test_body_deterministic_fail_in_execution_points() -> None:
    assert "body.deterministic_fail" in SPINE_EXECUTION_POINTS


def test_terminal_commit_in_event_categories() -> None:
    assert "spine.terminal.commit" in SPINE_EVENT_CATEGORIES


def test_body_deterministic_fail_in_event_categories() -> None:
    assert "spine.body.deterministic_fail" in SPINE_EVENT_CATEGORIES


def test_terminal_commit_completed_maps_to_completed_outcome() -> None:
    from lca.plugins.session.derivers.step_tree.journal_fold import (
        _StepTreeState,
        _capture_outcome,
    )

    state = _StepTreeState()
    _capture_outcome(state, "spine.terminal.commit", {"outcome": "completed", "reason": ""})
    assert state.terminal_outcome == "completed"


def test_terminal_commit_budget_exhausted_maps_to_budget_exhausted() -> None:
    from lca.plugins.session.derivers.step_tree.journal_fold import (
        _StepTreeState,
        _capture_outcome,
    )

    state = _StepTreeState()
    _capture_outcome(state, "spine.terminal.commit", {"outcome": "failed", "reason": "budget_exceeded"})
    assert state.terminal_outcome == "budget_exhausted"


def test_body_deterministic_fail_maps_to_failed() -> None:
    from lca.plugins.session.derivers.step_tree.journal_fold import (
        _StepTreeState,
        _capture_outcome,
    )

    state = _StepTreeState()
    _capture_outcome(state, "spine.body.deterministic_fail", {"tool_name": "cat", "error": "No such file"})
    assert state.terminal_outcome == "failed"