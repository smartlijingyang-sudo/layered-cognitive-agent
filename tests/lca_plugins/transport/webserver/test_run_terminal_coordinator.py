"""Tests for the unified RunTerminalCoordinator (INV-ARCH-01, INV-ARCH-02)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.observability.registry.status import RunLifecycleStatus
from lca.plugins.transport.webserver.carrier.runs.execute.loop_drivers import DriverOutcome
from lca.plugins.transport.webserver.handlers.runs.terminal.lifecycle import (
    RunTerminalCoordinator,
)


def _make_mock_session(*, cancel_requested: bool = False, error: str = "") -> Any:
    session = MagicMock()
    session.run_id = "test-run-123"
    session.trace_id = "trace-456"
    session.agent = MagicMock()
    session.agent.name = "test-agent"
    session.mode = "standard"
    session.user_text = "test query"
    session.hub = None
    session.cancel_requested = cancel_requested
    session.task = None
    session.error = error
    session.status = RunLifecycleStatus.RUNNING
    session.closed_at = None
    return session


@pytest.mark.asyncio
async def test_inv_arch_01_terminalize_success_sets_completed() -> None:
    session = _make_mock_session()
    registry = MagicMock()
    finalizer_called = []

    async def mock_finalizer(run_id: str) -> None:
        finalizer_called.append(run_id)

    coordinator = RunTerminalCoordinator(registry, finalizer=mock_finalizer, materializer=lambda _s: None)
    await coordinator.terminalize(session, success=True)

    assert session.status == RunLifecycleStatus.COMPLETED
    assert finalizer_called == ["test-run-123"]
    registry.clear_inflight.assert_called_once_with("test-run-123")
    registry.prune.assert_called_once()
    session.close.assert_called_once_with("completed")


@pytest.mark.asyncio
async def test_inv_arch_01_terminalize_failure_sets_failed() -> None:
    session = _make_mock_session(error="Critical runtime error")
    registry = MagicMock()

    coordinator = RunTerminalCoordinator(registry, finalizer=lambda _id: None, materializer=lambda _s: None)
    await coordinator.terminalize(session, success=False)

    assert session.status == RunLifecycleStatus.FAILED
    session.close.assert_called_once_with("error")


def test_inv_arch_02_apply_driver_outcome_waiting_input() -> None:
    session = _make_mock_session()
    registry = MagicMock()
    coordinator = RunTerminalCoordinator(registry)

    outcome = DriverOutcome(
        success=False,
        waiting_input=True,
        resumable=MagicMock(),
        snapshot={"step": 1},
        approval_request="need confirmation",
    )

    paused = coordinator.apply_driver_outcome(session, outcome)

    assert paused is True
    assert session.status == RunLifecycleStatus.WAITING_INPUT
    assert session.snapshot == {"step": 1}
    assert session.approval_request == "need confirmation"


def test_inv_arch_02_apply_driver_outcome_completed_returns_false() -> None:
    session = _make_mock_session()
    registry = MagicMock()
    coordinator = RunTerminalCoordinator(registry)

    outcome = DriverOutcome(
        success=True,
        waiting_input=False,
    )

    paused = coordinator.apply_driver_outcome(session, outcome)

    assert paused is False
    assert session.status == RunLifecycleStatus.RUNNING


def test_inv_arch_02_apply_resume_outcome_input_required() -> None:
    session = _make_mock_session()
    registry = MagicMock()
    coordinator = RunTerminalCoordinator(registry)

    result = MagicMock()
    result.status = TaskStatus.INPUT_REQUIRED
    result.extra = {"state_snapshot": {"count": 2}, "approval_request": "approved?"}

    needs_input = coordinator.apply_resume_outcome(session, result)

    assert needs_input is True
    assert session.status == RunLifecycleStatus.WAITING_INPUT
    assert session.snapshot == {"count": 2}
    assert session.approval_request == "approved?"
def test_ra178_both_pause_paths_capture_identical_fact_sets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RA-178: fresh pause and resume-then-pause-again capture identical facts.

    The pause-fact pairing lives in _capture_defer_pause_facts; both pause
    paths must converge on the same fact set so a future third fact cannot
    land on one path and be forgotten on the other.
    """
    from lca.plugins.transport.webserver.handlers.runs.terminal import (
        lifecycle as _lc,
    )

    monkeypatch.setattr(
        _lc, "_capture_loaded_namespaces", lambda: frozenset({"shell", "file"})
    )
    monkeypatch.setattr(
        _lc, "_capture_namespace_approval", lambda: {"shell": "allow"}
    )

    coordinator = RunTerminalCoordinator(MagicMock())

    # Fresh pause via the driver outcome path.
    driver_session = _make_mock_session()
    outcome = DriverOutcome(
        success=False,
        waiting_input=True,
        resumable=MagicMock(),
        snapshot={"step": 1},
        approval_request="need confirmation",
    )
    assert coordinator.apply_driver_outcome(driver_session, outcome) is True

    # Resume-then-pause-again via the resume outcome path.
    resume_session = _make_mock_session()
    result = MagicMock()
    result.status = TaskStatus.INPUT_REQUIRED
    result.extra = {"state_snapshot": {"count": 2}, "approval_request": "approved?"}
    assert coordinator.apply_resume_outcome(resume_session, result) is True

    expected = (frozenset({"shell", "file"}), {"shell": "allow"})
    assert (
        driver_session.loaded_namespaces,
        driver_session.namespace_approval,
    ) == expected
    assert (
        resume_session.loaded_namespaces,
        resume_session.namespace_approval,
    ) == expected
