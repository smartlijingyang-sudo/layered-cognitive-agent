"""Focused tests for ``spine.sink.file`` and ``spine.sink.console`` plugins."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.sinks.file_sink import FileSink
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
        "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        "when_corrected": datetime(2026, 9, 1, 12, 0, 0, 100000, tzinfo=timezone.utc),
        "prev_event_hash": None,
        "run_id": "r1",
        "step_id": "s1",
        "payload": {"x": 1},
    }
    base.update(overrides)
    return EventRecord(**base)


def test_file_setup_provides_file_sink(tmp_path: Path) -> None:
    """``spine.sink.file`` setup MUST provide a ``FileSink`` under ``file_sink``."""
    ctx = _StubPluginContext()
    events_path = tmp_path / "spine" / "events.jsonl"
    asyncio.run(
        file_setup.setup(
            ctx,
            {"path": str(events_path), "run_id": "test-run"},
        )
    )

    assert "file_sink" in ctx.provided
    sink = ctx.provided["file_sink"]
    assert isinstance(sink, FileSink)
    assert sink.path == events_path


def test_file_sink_plugin_writes_a_line(tmp_path: Path) -> None:
    """Provided FileSink MUST append one JSONL line for a written record."""
    ctx = _StubPluginContext()
    events_path = tmp_path / "events.jsonl"
    asyncio.run(file_setup.setup(ctx, {"path": str(events_path), "run_id": "boot"}))
    sink: FileSink = ctx.provided["file_sink"]
    sink.write(_make_rec())
    sink.close()

    lines = events_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["execution_point"] == "brain.think.start"
    assert obj["run_id"] == "r1"


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
