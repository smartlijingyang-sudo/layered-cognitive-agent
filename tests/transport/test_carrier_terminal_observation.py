"""Carrier terminal observation must resolve both Session wrapper shapes.

``lca/plugins/transport/webserver/handlers/runs/terminal/observation.py`` is the
carrier-side guard (:class:`lca.session.lifecycle.bind.BoundRunEventSession` and
:class:`lca.session.lifecycle.bind.RunEventSessionBridge`) that decides whether a
run already recorded a terminal container event. If the read misses,
``emit_carrier_run_failed`` appends a second ``RuntimeObserved(run.lifecycle.failed)
/ AgentRunFinished`` for a run the cognitive agent already closed — a duplicate
terminal fact on the SSOT log.
"""

from __future__ import annotations

from types import SimpleNamespace

from lca.plugins.transport.webserver.handlers.runs.terminal import observation


def _session(*event_types: str) -> SimpleNamespace:
    events = [SimpleNamespace(type=t) for t in event_types]
    return SimpleNamespace(snapshot_events=lambda: events)


def test_direct_bridge_shape_reads_session_events():
    session = SimpleNamespace(event_session=SimpleNamespace(inner=_session("AgentRunFinished")))
    assert observation.journal_has_terminal_event(session) is True


def test_bound_session_shape_reads_through_bridge():
    """``BoundRunEventSession`` has ``.bridge``, never ``.inner``."""
    bridge = SimpleNamespace(inner=_session("StepRecorded", "TeamRunFinished"))
    session = SimpleNamespace(event_session=SimpleNamespace(bridge=bridge))
    assert observation.journal_has_terminal_event(session) is True


def test_non_terminal_events_do_not_count():
    session = SimpleNamespace(event_session=SimpleNamespace(inner=_session("StepRecorded")))
    assert observation.journal_has_terminal_event(session) is False


def test_unbound_session_reports_no_terminal_event():
    assert observation.journal_has_terminal_event(SimpleNamespace()) is False
