"""Focused tests for ``spine.sink.file`` and ``spine.sink.console`` plugins."""

from __future__ import annotations

import asyncio
import io
import json
from datetime import datetime, timezone, UTC
from pathlib import Path
from typing import Any

from lca.infrastructure.observability.spine.event.record import EventRecord
from lca.infrastructure.observability.spine.sinks.routing_file_sink import (
    RunRoutingFileSink,
)
from lca.plugins.observability.spine.sinks.console import ConsoleSink
from lca.plugins.observability.spine.sinks.console import setup as console_setup
from lca.plugins.observability.spine.sinks.file import setup as file_setup


class _StubPluginContext:
    """Minimal PluginContext stand-in that records ``provide`` calls."""

    def __init__(self) -> None:
        self.provided: dict[str, Any] = {}

    def provide(self, key: str, value: object, **kwargs: object) -> None:
        del kwargs
        self.provided[key] = value

    def require(self, key: str) -> Any:
        raise KeyError(key)

    def register(self, seam: str, name: str, value: object, **kwargs: object) -> None:
        del seam, name, value, kwargs


def _make_rec(**overrides: Any) -> EventRecord:
    base: dict[str, Any] = {
        "execution_point": "brain.think.start",
        "channel": "fact",
        "span_id": "01HM",
        "parent_span_id": None,
        "sequence": 1,
        "epoch": 1,
        "causality_id": "ca",
        "outcome": None,
        "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=UTC),
        "when_corrected": datetime(2026, 9, 1, 12, 0, 0, 100000, tzinfo=UTC),
        "prev_event_hash": None,
        "run_id": "r1",
        "step_id": "s1",
        "payload": {"x": 1},
    }
    base.update(overrides)
    return EventRecord(**base)


def test_file_setup_provides_routing_sink(tmp_path: Path) -> None:
    """``spine.sink.file`` setup MUST provide a ``RunRoutingFileSink``."""
    ctx = _StubPluginContext()
    boot = tmp_path / "spine" / "boot-spine.jsonl"
    runs = tmp_path / "traces" / "runs"
    asyncio.run(
        file_setup.setup(
            ctx,
            {"boot_path": str(boot), "runs_root": str(runs)},
        )
    )

    assert "file_sink" in ctx.provided
    sink = ctx.provided["file_sink"]
    assert isinstance(sink, RunRoutingFileSink)
    assert sink.boot_path == boot
    assert sink.runs_root == runs


def test_file_sink_plugin_routes_run_events(tmp_path: Path) -> None:
    """Run-scoped records MUST land under traces/runs/<run_id>/<run_id>.spine.jsonl。

    ADR-0169 PR-27:默认 file_name 模板 = ``$run_id.spine.jsonl``,
    实例化为 ``<run_id>.spine.jsonl``。
    """
    ctx = _StubPluginContext()
    boot = tmp_path / "boot-spine.jsonl"
    runs = tmp_path / "runs"
    asyncio.run(
        file_setup.setup(
            ctx,
            {"boot_path": str(boot), "runs_root": str(runs)},
        )
    )
    sink: RunRoutingFileSink = ctx.provided["file_sink"]
    sink.write(_make_rec(run_id="run_r1"))
    sink.close()

    path = runs / "run_r1" / "run_r1.spine.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["execution_point"] == "brain.think.start"
    assert obj["run_id"] == "run_r1"


def test_legacy_path_config_maps_to_boot_spine(tmp_path: Path) -> None:
    """Legacy ``path: .../events.jsonl`` MUST map to boot-spine.jsonl (PR-4 收口)。"""
    ctx = _StubPluginContext()
    legacy = tmp_path / "spine" / "events.jsonl"
    asyncio.run(file_setup.setup(ctx, {"path": str(legacy)}))
    sink: RunRoutingFileSink = ctx.provided["file_sink"]
    assert sink.boot_path.name == "boot-spine.jsonl"
    sink.close()


def test_console_setup_provides_console_sink() -> None:
    """``spine.sink.console`` setup MUST provide under ``console_sink``."""
    ctx = _StubPluginContext()
    asyncio.run(console_setup.setup(ctx, {}))

    assert "console_sink" in ctx.provided
    assert isinstance(ctx.provided["console_sink"], ConsoleSink)


def test_console_sink_write_does_not_raise() -> None:
    """``ConsoleSink.write`` MUST NOT raise for a normal EventRecord."""
    sink = ConsoleSink()
    sink.write(_make_rec())
    sink.close()


def test_file_and_console_setup_are_plugin_carriers() -> None:
    """Both modules MUST expose plugin-decorated ``setup`` carriers."""
    assert hasattr(file_setup, "setup")
    assert callable(file_setup.setup)
    assert hasattr(console_setup, "setup")
    assert callable(console_setup.setup)


GRAPH_PAYLOAD: dict[str, Any] = {
    "kind": "visit_end",
    "plan_ref": "think.subgraph",
    "node_id": "think.reason.llm",
    "node_index": 1,
    "depth": 2,
    "binding": "node_executor",
    "edge_id": "",
    "from_node": "",
    "to_node": "",
    "dispatch": "next",
    "outcome": "success",
    "error": "",
    "elapsed_ms": 604,
    "inputs": {"context": ["a"]},
    "outputs": {"decision": {"kind": "answer"}},
    "metadata": {"binding": "node_executor"},
}


def _graph_rec(**overrides: Any) -> EventRecord:
    base: dict[str, Any] = {
        "execution_point": "phase_graph.node.end",
        "payload": dict(GRAPH_PAYLOAD),
        "run_id": "run_live",
        "sequence": 44,
    }
    base.update(overrides)
    return _make_rec(**base)


def test_console_graph_timeline_writes_one_compact_line() -> None:
    """The live line names the graph, the node, the timing and the ports.

    ``run=``/``seq=`` come from the ``EventRecord`` the spine hands over, which
    is what makes this line quotable against the durable record later.
    """
    stream = io.StringIO()

    ConsoleSink(stream, format="graph_timeline").write(_graph_rec())

    assert stream.getvalue() == (
        "run=run_live  seq=44  phase_graph.node.end  node=think.reason.llm"
        "  ok  604ms  depth=2  dispatch=next  in=context  out=decision\n"
    )
    assert "answer" not in stream.getvalue()


def test_console_graph_timeline_drops_every_other_event() -> None:
    """Narrowing the stream is the point; the full payload stays in the spine file.

    ``phase_graph.instrument.coverage`` shares the ``phase_graph.`` prefix but is
    not a lifecycle event, so it pins exact matching rather than prefix matching.
    """
    stream = io.StringIO()
    sink = ConsoleSink(stream, format="graph_timeline")

    sink.write(_graph_rec(execution_point="phase_graph.instrument.coverage"))
    sink.write(_graph_rec(execution_point="llm.stream.token"))

    assert stream.getvalue() == ""


def test_console_default_format_still_writes_full_jsonl() -> None:
    """Default is unchanged, so existing machine consumers see no difference."""
    stream = io.StringIO()

    ConsoleSink(stream).write(_graph_rec())

    written = json.loads(stream.getvalue())
    assert written["execution_point"] == "phase_graph.node.end"
    assert written["payload"]["outputs"] == {"decision": {"kind": "answer"}}


def test_console_setup_reads_the_bundle_format_config() -> None:
    """``config.format`` selects the projection, so the bundle owns the choice."""
    timeline_ctx = _StubPluginContext()
    asyncio.run(console_setup.setup(timeline_ctx, {"format": "graph_timeline"}))
    jsonl_ctx = _StubPluginContext()
    asyncio.run(console_setup.setup(jsonl_ctx, {}))

    assert timeline_ctx.provided["console_sink"]._format == "graph_timeline"
    assert jsonl_ctx.provided["console_sink"]._format == "jsonl"


def test_console_graph_timeline_still_swallows_sink_failures() -> None:
    """A broken stream must not reach the spine hot path in either format."""
    sink = ConsoleSink(io.StringIO(), format="graph_timeline")
    sink._stream = None  # type: ignore[assignment]

    sink.write(_graph_rec())


def test_console_write_event_renders_timeline_line_from_event_id() -> None:
    """Session-observer entrypoint: join keys come from ``<run_id>:<seq>``.

    Bypasses ``EventRecord.__post_init__`` so a Session observer can drive
    the live stream without rebuilding the strict record shape.
    """
    stream = io.StringIO()
    sink = ConsoleSink(stream, format="graph_timeline")

    sink.write_event(
        "phase_graph.node.end",
        dict(GRAPH_PAYLOAD),
        "run_abc:44",
    )

    assert stream.getvalue() == (
        "run=run_abc  seq=44  phase_graph.node.end  node=think.reason.llm"
        "  ok  604ms  depth=2  dispatch=next  in=context  out=decision\n"
    )


def test_console_write_event_drops_non_graph_events_in_timeline_format() -> None:
    """graph_timeline narrowing still applies on the Session observer path."""
    stream = io.StringIO()
    sink = ConsoleSink(stream, format="graph_timeline")

    sink.write_event("llm.stream.token", {"text": "hi"}, "run_abc:1")

    assert stream.getvalue() == ""


def test_console_setup_registers_session_observer() -> None:
    """setup writes the sink under ``console_sink`` AND into the observer catalog.

    The catalog is the production wiring (ADR-0186 / spine_file_sink
    precedent): the live EventSpine does not wire this sink itself because
    the DAG runs ``spine.core`` before ``spine.sink.console``, so the
    observer registration is what carries events to stdout in a real run.
    """
    from lca.plugins.events._session_observe import (
        clear_observer_catalog,
        observer_catalog,
    )

    clear_observer_catalog()
    try:
        ctx = _StubPluginContext()
        asyncio.run(console_setup.setup(ctx, {"format": "graph_timeline"}))

        catalog = observer_catalog()
        assert len(catalog) == 1, (
            f"console sink must register exactly one Session observer; got {list(catalog)!r}"
        )
        registered_sink = ctx.provided["console_sink"]
        assert isinstance(registered_sink, ConsoleSink)
        _, callback = next(iter(catalog.items()))
        stream = io.StringIO()
        registered_sink._stream = stream  # type: ignore[assignment]
        callback(
            type(
                "P",
                (),
                {
                    "execution_point": "phase_graph.node.start",
                    "payload": dict(GRAPH_PAYLOAD),
                },
            )(),
            type("R", (), {"event_id": "run_e2e:1"})(),
        )
        assert stream.getvalue().startswith(
            "run=run_e2e  seq=1  phase_graph.node.start"
        )
    finally:
        clear_observer_catalog()
