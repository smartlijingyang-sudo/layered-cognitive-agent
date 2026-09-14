"""Terminal observation + NullHookRegistry tests (SSOT: Session.append)."""

from __future__ import annotations

import json
from pathlib import Path

from lca.contracts.models.observability.event.event import OperationOutcome, RuntimeKind
from lca.contracts.models.observability.journal.journal import (
    AgentRunFinished,
    RuntimeObserved,
)
from lca.plugins.transport.webserver.handlers.runs.session.session.session import RunSession
from lca.plugins.transport.webserver.handlers.runs.terminal.observation import (
    emit_carrier_run_failed,
    is_carrier_terminal_observed,
    journal_has_terminal_event,
)
from lca.runtime.support.null_hook_registry import NullHookRegistry
from lca.session.append import Session


def _session_with_session(*, run_id: str, session: Session | None = None) -> RunSession:
    from lca.infrastructure.observability.journal.stream.live_tail import LiveTail

    bridge = None
    if session is not None:
        from lca.session.lifecycle.bind import RunEventSessionBridge

        bridge = RunEventSessionBridge(session)
    return RunSession(
        run_id=run_id,
        trace_id=f"trace-{run_id}",
        spine_path=Path("/tmp/nonexistent.spine.jsonl"),
        tail=LiveTail(),
        question="q",
        user_text="u",
        mode="solo",
        event_session=bridge,
    )


def _session(*, run_id: str, hub: object) -> RunSession:
    """Compat shim:hub.journal.write 路径已退役 —— 测试改写为 Session。

    保留函数签名以最小化测试改动:``hub`` 仅作占位参数。
    """
    return _session_with_session(run_id=run_id)


def test_null_hook_registry_trigger_is_noop() -> None:
    import asyncio

    hooks = NullHookRegistry()

    async def _run() -> None:
        await hooks.trigger("on_start", object())  # type: ignore[arg-type]

    asyncio.run(_run())


def test_journal_has_terminal_event_detects_agent_run_finished() -> None:
    from lca.infrastructure.observability.facade.facade.facade import record as _record
    from lca.plugins.events.publishers._session_publish import (
        current_publish_session,
        set_publish_session,
    )

    session = Session(f"run-t1-{id(object())}")
    token = set_publish_session(session)
    try:
        _record(AgentRunFinished(status="failed", error="boom"))
        run_session = _session_with_session(run_id="run-t1", session=session)
        assert journal_has_terminal_event(run_session) is True
    finally:
        from lca.plugins.events.publishers._session_publish import reset_publish_session

        reset_publish_session(token)
        # Verify unbound state for downstream tests.
        assert current_publish_session() is None


def test_emit_carrier_run_failed_skips_when_terminal_exists() -> None:
    from lca.infrastructure.observability.facade.facade.facade import record as _record
    from lca.plugins.events.publishers._session_publish import (
        reset_publish_session,
        set_publish_session,
    )

    session = Session(f"run-t2-{id(object())}")
    token = set_publish_session(session)
    try:
        _record(AgentRunFinished(status="failed", error="already"))
        run_session = _session_with_session(run_id="run-t2", session=session)
        assert emit_carrier_run_failed(run_session, user_message="late") is None
    finally:
        reset_publish_session(token)


def test_is_carrier_terminal_observed() -> None:
    event = RuntimeObserved(
        kind=RuntimeKind.ERROR,
        operation="run.lifecycle.failed",
        outcome=OperationOutcome.ERROR,
        error_message="ValidationError: x",
    )
    assert is_carrier_terminal_observed(event) is True


def test_failure_reader_loads_exception_message(tmp_path) -> None:
    from lca.plugins.transport.webserver.read.runs.failure.failure_reader import (
        failure_summary_for_run,
        load_exception_records,
    )

    run_id = "run_exc_test"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    line = (
        '{"execution_point":"exception.caught","payload":{'
        '"exception_class":"ValidationError",'
        '"exception_message":"bad ep",'
        '"traceback_text":"Traceback:\\n  File \\"x\\"\\nValidationError: bad ep\\n",'
        '"err_kind":"unknown","boundary":"lifecycle.execute"}}'
    )
    (run_dir / f"{run_id}.exceptions.jsonl").write_text(line + "\n", encoding="utf-8")
    records = load_exception_records(run_id, traces_root=tmp_path / "runs")
    assert len(records) == 1
    assert records[0]["exception_message"] == "bad ep"
    assert "Traceback:" in records[0]["traceback_text"]
    summary = failure_summary_for_run(run_id, user_error="用户可见", traces_root=tmp_path / "runs")
    assert summary["exception_class"] == "ValidationError"
    assert summary["has_traceback"] is True


def test_unused_helper_no_crash() -> None:
    """Suppress unused import warnings."""
    json.dumps({})
