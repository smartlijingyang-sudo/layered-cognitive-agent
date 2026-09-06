from types import SimpleNamespace

from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.plugins.transport.webserver.carrier.runs.execute.loop_drivers import DriverOutcome
from lca.plugins.transport.webserver.handlers.runs.session.session.session import (
    RunSession,
    RunStatus,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.outcome.outcome import RunOutcomeApplier


def _session() -> RunSession:
    return RunSession(
        run_id="run-1",
        trace_id="trace-1",
        spine_path=None,  # type: ignore[arg-type]
        tail=None,  # type: ignore[arg-type]
        question="question",
        user_text="user text",
        mode="solo",
    )


def test_apply_driver_pauses_without_terminalizing() -> None:
    session = _session()
    resumable = object()

    paused = RunOutcomeApplier().apply_driver(
        session,
        DriverOutcome(
            success=False,
            waiting_input=True,
            snapshot={"cursor": 1},
            approval_request={"type": "confirm"},
            resumable=resumable,
        ),
    )

    assert paused is True
    assert session.status is RunStatus.WAITING_INPUT
    assert session.snapshot == {"cursor": 1}
    assert session.approval_request == {"type": "confirm"}
    assert session.runnable is resumable


def test_apply_driver_does_not_mutate_session_error() -> None:
    session = _session()

    paused = RunOutcomeApplier().apply_driver(
        session,
        DriverOutcome(success=False, error="bad input"),
    )

    assert paused is False
    assert session.status is RunStatus.PENDING
    assert session.error == ""


def test_apply_resume_projects_input_required_and_completion() -> None:
    session = _session()
    applier = RunOutcomeApplier()

    paused = applier.apply_resume(
        session,
        SimpleNamespace(
            status=TaskStatus.INPUT_REQUIRED,
            extra={"state_snapshot": "snapshot", "approval_request": {"type": "confirm"}},
            error="",
        ),
    )

    assert paused is True
    assert session.status is RunStatus.WAITING_INPUT
    assert session.snapshot == "snapshot"
    assert session.approval_request == {"type": "confirm"}

    session.status = RunStatus.RUNNING
    paused = applier.apply_resume(
        session,
        SimpleNamespace(status=TaskStatus.COMPLETED, extra={}, error=""),
    )
    assert paused is False
    assert session.status is RunStatus.RUNNING
