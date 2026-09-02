"""Focused tests for ``spine.sink.file`` and ``spine.sink.console`` plugins."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lca.infrastructure.observability.spine.event_record import EventRecord
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
        "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        "when_corrected": datetime(2026, 9, 1, 12, 0, 0, 100000, tzinfo=timezone.utc),
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
    boot = tmp_path / "spine" / "boot-events.jsonl"
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
    boot = tmp_path / "boot-events.jsonl"
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


def test_legacy_path_config_maps_to_boot_events(tmp_path: Path) -> None:
    """Legacy ``path: .../events.jsonl`` MUST map to boot-events.jsonl."""
    ctx = _StubPluginContext()
    legacy = tmp_path / "spine" / "events.jsonl"
    asyncio.run(file_setup.setup(ctx, {"path": str(legacy)}))
    sink: RunRoutingFileSink = ctx.provided["file_sink"]
    assert sink.boot_path.name == "boot-events.jsonl"
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
