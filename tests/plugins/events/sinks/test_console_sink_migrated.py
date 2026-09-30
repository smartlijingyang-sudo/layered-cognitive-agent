"""Behavioral tests for the migrated spine sink plugins.

The file/console sink plugins moved from the COMPAT package into
``lca.plugins.events.sinks``; these tests exercise the shipped ``ConsoleSink``
through its new import path.
"""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime

from lca.infrastructure.observability.spine.event.record import EventRecord
from lca.plugins.events.sinks.console_sink import ConsoleSink


def _record(execution_point: str = "think.gate.start") -> EventRecord:
    return EventRecord(
        execution_point=execution_point,
        channel="fact",
        span_id="01HM",
        parent_span_id=None,
        sequence=1,
        epoch=1,
        causality_id="ca",
        outcome=None,
        when=datetime(2026, 9, 1, 12, 0, 0, tzinfo=UTC),
        when_corrected=datetime(2026, 9, 1, 12, 0, 0, 100000, tzinfo=UTC),
        prev_event_hash=None,
        run_id="r1",
        step_id="s1",
        payload={"x": 1},
    )


def test_console_sink_jsonl_write_does_not_raise() -> None:
    stream = io.StringIO()
    sink = ConsoleSink(stream=stream)
    sink.write(_record())
    # JSONL output is parseable.
    line = stream.getvalue().strip()
    parsed = json.loads(line)
    assert parsed["execution_point"] == "think.gate.start"


def test_console_sink_graph_timeline_write() -> None:
    stream = io.StringIO()
    sink = ConsoleSink(stream=stream, format="graph_timeline")
    sink.write(_record(execution_point="phase_graph.node.start"))
    assert stream.getvalue()  # non-empty line
    sink.write(_record(execution_point="phase_graph.node.end"))
    assert len(stream.getvalue().strip().splitlines()) == 2


def test_console_sink_write_swallows_errors() -> None:
    """``write`` must never raise (best-effort stdout sink)."""
    sink = ConsoleSink(stream=None, format="jsonl")  # type: ignore[arg-type]
    # A valid record writes to sys.stdout without raising.
    sink.write(_record())


def test_console_sink_is_exported_from_new_path() -> None:
    import lca.plugins.events.sinks.console_sink as module

    assert module.ConsoleSink is ConsoleSink
    assert "setup" in module.__all__
