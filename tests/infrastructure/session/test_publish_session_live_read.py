"""Regression lock: ``Session bindings.resolve_session_reader`` must observe
live updates to ``_session_publish._ACTIVE_SESSION``.

The publish Session is a process-wide module global. When ``set_publish_session``
reassigns it, every consumer that reads via the module attribute sees the
new value. A consumer that captured the value at import time via
``from lca.plugins.events.publishers._session_publish import _ACTIVE_SESSION``
keeps the stale initial ``None`` and never sees updates.

Before the fix, ``record(AgentRunStarted)`` raised
``requires a bound Session`` at the start of every backend run because
``infrastructure.session.bindings`` had stale-captured the ``None`` value at
import time. This test pins the live-read invariant.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lca.infrastructure.session import bindings
from lca.loop import fact_gateway
from lca.loop.emit.spine.ep import publish_spine_ep
from lca.plugins.events.publishers import _session_publish
from lca.session.append import Session
from lca.session.lifecycle.bind import RunEventSessionBridge

if TYPE_CHECKING:
    import pytest


def test_resolve_session_reader_sees_set_publish_session() -> None:
    """``set_publish_session(s)`` then ``bindings._active_publish_session()``
    returns ``s``, not the import-time-captured ``None``.
    """
    sentinel = object()
    try:
        _session_publish.set_publish_session(sentinel)
        assert bindings._active_publish_session() is sentinel
        assert _session_publish._ACTIVE_SESSION is sentinel
    finally:
        _session_publish.reset_publish_session(None)


def test_resolve_session_reader_returns_none_after_reset() -> None:
    """``reset_publish_session`` is observed immediately by live readers."""
    _session_publish.set_publish_session(object())
    _session_publish.reset_publish_session(None)
    assert bindings._active_publish_session() is None
    assert bindings.resolve_session_reader() is None


def test_active_publish_session_does_not_capture_stale_value() -> None:
    """A second ``set_publish_session`` overrides a previous binding even
    though ``bindings`` was imported before either call.
    """
    first = object()
    second = object()
    try:
        _session_publish.set_publish_session(first)
        assert bindings._active_publish_session() is first
        _session_publish.set_publish_session(second)
        assert bindings._active_publish_session() is second
        assert bindings._active_publish_session() is not first
    finally:
        _session_publish.reset_publish_session(None)


# ── FactGateway: same invariant, the durable-fact gate ──────────────────────
#
# ``publish_ep_bound`` / ``append_catalog_bound`` are the single write gate for
# every spine EP (``llm.call.*``, ``step.tool_*.record``, ``kernel.run.*``,
# ``body.*``, ``phase.*.fold``). They resolve the writer by falling back to the
# active binding, so a snapshot of that binding freezes ``None`` and the whole
# journal chain silently produces nothing — the exact failure that emptied
# ``journal.steps`` for live runs after the ContextVar deletion.


def _bind_run_bridge(run_id: str) -> RunEventSessionBridge:
    """Bind the shipped run publisher as the active publish Session."""
    bridge = RunEventSessionBridge(Session(run_id))
    _session_publish.set_publish_session(bridge)
    return bridge


def test_publish_spine_ep_reaches_session_bound_after_import() -> None:
    """A spine EP emitted after ``set_publish_session`` lands in the Session log.

    Drives the shipped gate (:func:`publish_spine_ep`) into the shipped
    publisher (``RunEventSessionBridge`` → ``Session.append``) — the same bytes
    the journal fold and the spine ledger later read.
    """
    bridge = _bind_run_bridge("run_live_read_llm")
    try:
        ref = publish_spine_ep(
            "llm.call.start",
            {"model": "test-model", "stream": True, "prompt_preview": "hi"},
            actor="llm",
        )
        assert ref is not None, "publish_ep_bound dropped a fact while a Session was bound"
        events = bridge.inner.snapshot_events()
        assert [e.type for e in events] == ["spine.llm.call.start"]
        assert events[0].data["model"] == "test-model"
    finally:
        _session_publish.reset_publish_session(None)


def test_rebinding_session_reroutes_spine_ep_to_new_run() -> None:
    """A second run's binding wins: the gate is not frozen on the first Session."""
    first = _bind_run_bridge("run_live_read_first")
    publish_spine_ep("kernel.run.start", {"run_id": "a", "trace_id": ""}, actor="transport")
    second = _bind_run_bridge("run_live_read_second")
    try:
        publish_spine_ep(
            "kernel.run.stop", {"run_id": "b", "outcome": "success"}, actor="transport"
        )
        assert [e.type for e in second.inner.snapshot_events()] == ["spine.kernel.run.stop"]
        assert [e.type for e in first.inner.snapshot_events()] == ["spine.kernel.run.start"]
    finally:
        _session_publish.reset_publish_session(None)


def test_unbound_durable_fact_drop_is_loud(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No Session bound ⇒ the drop is reported, never silent."""
    assert publish_spine_ep("llm.call.start", {"model": "m"}, actor="llm") is None
    captured = capsys.readouterr()
    assert "fact_gateway.unbound_drop" in captured.out + captured.err


def test_fact_gateway_holds_no_import_time_session_snapshot() -> None:
    """Structural lock: the gate must not re-bind the mutable global by value."""
    assert not hasattr(fact_gateway, "_ACTIVE_SESSION"), (
        "fact_gateway captured _ACTIVE_SESSION at import time; late "
        "set_publish_session bindings would be invisible and spine EPs dropped"
    )
