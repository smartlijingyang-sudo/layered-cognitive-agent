"""Direct unit tests for the converged run-failure observation seam (RA-048).

``RunLifecycleCoordinator._observe_failure`` concentrates the three inline
failure rituals (``execute()`` x2, ``resume()``); these tests drive it with a
fake session and assert the exact emit set for ``emit_finally=True`` vs
``False`` so the per-path emit sets stay bit-identical by construction.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

# isort: off
# Importing the terminal commands first initialises the execute package in the
# app's order and avoids the lifecycle<->execute circular import that occurs
# when lifecycle.lifecycle is the first module loaded.
from lca.plugins.transport.webserver.handlers.runs.terminal.registry import commands as registry_commands  # noqa: F401
from lca.plugins.transport.webserver.carrier.runs.lifecycle import lifecycle as lifecycle_module
# isort: on


def _coordinator() -> lifecycle_module.RunLifecycleCoordinator:
    return lifecycle_module.RunLifecycleCoordinator(registry=object())


def _session() -> SimpleNamespace:
    return SimpleNamespace(run_id="run-048", trace_id="trace-048", error=None)


def _drive(
    monkeypatch: Any, *, emit_finally: bool, boundary: str
) -> tuple[SimpleNamespace, Exception, Any, list[tuple], list[tuple]]:
    """Drive _observe_failure with all emits + _record_failure stubbed."""
    calls: list[tuple] = []
    recorded: list[tuple] = []
    session = _session()
    exc = ValueError("boom")
    hub = object()
    monkeypatch.setattr(
        lifecycle_module, "exc_to_record", lambda e, **kw: ("record", e, kw)
    )
    monkeypatch.setattr(
        lifecycle_module,
        "emit_exception_caught",
        lambda record: calls.append(("exception_caught", record)),
    )
    monkeypatch.setattr(
        lifecycle_module,
        "emit_carrier_run_failed",
        lambda s, **kw: calls.append(("carrier_run_failed", s, kw)),
    )
    monkeypatch.setattr(
        lifecycle_module,
        "emit_carrier_exception_finally",
        lambda **kw: calls.append(("exception_finally", kw)),
    )
    monkeypatch.setattr(
        lifecycle_module.RunLifecycleCoordinator,
        "_record_failure",
        staticmethod(lambda s, e, h, **kw: recorded.append((s, e, h, kw))),
    )
    _coordinator()._observe_failure(
        session,
        exc,
        boundary=boundary,
        hub=hub,
        user_message="user-visible message",
        emit_finally=emit_finally,
    )
    return session, exc, hub, calls, recorded


def test_observe_failure_with_finally_emits_full_set(monkeypatch: Any) -> None:
    session, exc, hub, calls, recorded = _drive(
        monkeypatch, emit_finally=True, boundary="lifecycle.execute"
    )
    assert [kind for kind, *_ in calls] == [
        "exception_caught",
        "carrier_run_failed",
        "exception_finally",
    ]
    # _record_failure gets session/exc/hub and the user message as error.
    assert recorded == [(session, exc, hub, {"error": "user-visible message"})]
    # exception-caught record carries the exception, boundary, and ids.
    _kind, record = calls[0]
    _tag, record_exc, record_kw = record
    assert record_exc is exc
    assert record_kw["boundary"] == "lifecycle.execute"
    assert record_kw["run_id"] == "run-048"
    assert record_kw["trace_id"] == "trace-048"
    # carrier run_failed carries the user message and exception class.
    _kind, failed_session, failed_kw = calls[1]
    assert failed_session is session
    assert failed_kw["user_message"] == "user-visible message"
    assert failed_kw["exception_class"] == "ValueError"
    # finally-emit carries the same boundary and trace id.
    _kind, finally_kw = calls[2]
    assert finally_kw == {"boundary": "lifecycle.execute", "trace_id": "trace-048"}


def test_observe_failure_without_finally_skips_finally_emit(
    monkeypatch: Any,
) -> None:
    session, exc, hub, calls, recorded = _drive(
        monkeypatch, emit_finally=False, boundary="lifecycle.resume"
    )
    assert [kind for kind, *_ in calls] == [
        "exception_caught",
        "carrier_run_failed",
    ]
    assert recorded == [(session, exc, hub, {"error": "user-visible message"})]
    # boundary label stays the resume one.
    _kind, record = calls[0]
    assert record[2]["boundary"] == "lifecycle.resume"
    _kind, failed_session, failed_kw = calls[1]
    assert failed_session is session
    assert failed_kw["exception_class"] == "ValueError"
