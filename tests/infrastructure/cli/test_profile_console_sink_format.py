"""``web-standard`` / ``oii-debug`` profiles must opt console sink into ``graph_timeline``.

The ``spine.sink.console`` plugin already supports ``format="graph_timeline"``,
but the bundle default is ``format="jsonl"`` so machine consumers are
unaffected. The ``web-standard`` profile is the deployment profile operators
watch live runs through, so it is where the live-timeline choice has to land
— via the profile ``patch:`` block, which is the LCA-standard mechanism (and
which already overrides ``spine.sink.file`` config).

Without the patch, the console stream is unreadable during a run; with it,
the same line format that ``trace-show`` and ``run-replay --show-graph``
print is what an operator sees live, so quoting one line to an agent is
quotable end-to-end.
"""

from __future__ import annotations

import asyncio
import io
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from lca.harness.profile.resolve.resolve import ResolvedProfile, resolve_profile
from lca.plugins.observability.spine.sinks.console import ConsoleSink
from lca.plugins.observability.spine.sinks.console import setup as console_setup

# Reuse the existing sink-test fixtures; they already pin the payload shape
# that ``graph_timeline.render_line`` is verified against.
from tests.lca_plugins.observability.spine.test_sinks import _make_rec

_REPO_ROOT = Path(__file__).resolve().parents[3]
_WEB_STANDARD_PROFILE = _REPO_ROOT / "profiles" / "web-standard.yaml"
_OII_DEBUG_PROFILE = _REPO_ROOT / "profiles" / "oii-debug.yaml"


def _console_config(resolved: ResolvedProfile) -> Mapping[str, Any]:
    """The resolved config the profile hands to ``spine.sink.console.setup``."""
    for plugin in resolved.plugins:
        if plugin.id == "spine.sink.console":
            return plugin.config
    raise AssertionError("spine.sink.console not in resolved profile plugins")


def _build_sink_from_config(config: Mapping[str, Any]) -> ConsoleSink:
    """Reproduce ``console_setup.setup(ctx, config)`` against a stub context."""

    class _StubCtx:
        def provide(self, key: str, value: object, **_kwargs: object) -> None:
            self.provided = {key: value}

        def require(self, key: str) -> Any:
            raise KeyError(key)

        def register(self, seam: str, name: str, value: object, **_kwargs: object) -> None:
            del seam, name, value

    ctx = _StubCtx()
    asyncio.run(console_setup.setup(ctx, config))
    sink = ctx.provided.get("console_sink")
    assert isinstance(sink, ConsoleSink), f"console_sink missing or wrong type: {ctx.provided!r}"
    return sink


def test_web_standard_profile_enables_graph_timeline_for_console_sink() -> None:
    """``web-standard`` MUST override ``spine.sink.console`` to ``graph_timeline``."""
    resolved = resolve_profile(_WEB_STANDARD_PROFILE)

    config = _console_config(resolved)
    assert config.get("format") == "graph_timeline", (
        "web-standard profile must patch spine.sink.console config.format to "
        f"'graph_timeline'; got {dict(config)!r}"
    )


def test_oii_debug_profile_yaml_patch_selects_graph_timeline() -> None:
    """``oii-debug`` profile YAML MUST carry the same console patch.

    Direct YAML read: the profile's resolve path is currently broken on an
    unrelated ``lca-llm-resolver`` patch (pre-existing on ``e3a4535b0``,
    unrelated to this fix). The patch entry itself is what this fix adds, so
    asserting it exists in the file is the direct verification. Resolved-config
    semantics are covered end-to-end by the ``web-standard`` test above.
    """
    raw = yaml.safe_load(_OII_DEBUG_PROFILE.read_text(encoding="utf-8"))
    patches = raw.get("patch") or []
    target = next((p for p in patches if p.get("id") == "spine.sink.console"), None)
    assert target is not None, (
        f"oii-debug.yaml must carry a patch entry for spine.sink.console; got patches={patches!r}"
    )
    assert target.get("config", {}).get("format") == "graph_timeline", (
        f"oii-debug spine.sink.console patch must set format=graph_timeline; "
        f"got {target.get('config')!r}"
    )


def test_resolved_console_sink_filters_non_graph_events_and_emits_one_line_per_graph_event() -> (
    None
):
    """The patched sink drops non-graph EPs and renders one compact line per graph EP.

    Reuses ``_make_rec`` from ``tests/lca_plugins/observability/spine/test_sinks.py``
    so the live line matches the byte shape ``trace-show`` already pins.
    """
    resolved = resolve_profile(_WEB_STANDARD_PROFILE)
    sink = _build_sink_from_config(_console_config(resolved))

    stream = io.StringIO()
    sink._stream = stream  # type: ignore[assignment]

    sink.write(
        _make_rec(
            execution_point="phase_graph.node.end",
            payload={
                "kind": "visit_end",
                "node_id": "phase.think.reason",
                "depth": 1,
                "binding": "node_executor",
                "outcome": "success",
                "error": "",
                "elapsed_ms": 12,
                "inputs": {"context": ["a"]},
                "outputs": {"decision": {"kind": "answer"}},
                "metadata": {"binding": "node_executor"},
            },
            run_id="run_live",
            sequence=1,
        )
    )
    sink.write(_make_rec(execution_point="llm.stream.token", sequence=2))

    written = stream.getvalue()
    lines = [line for line in written.split("\n") if line]
    assert len(lines) == 1, (
        f"graph_timeline must emit one line per graph EP and zero for others; got {lines!r}"
    )
    line = lines[0]
    assert "phase_graph.node.end" in line
    assert "node=phase.think.reason" in line
    assert "ok" in line
    assert "12ms" in line
    assert "run=run_live" in line
    assert "seq=1" in line
    assert "answer" not in line, "payload values must not leak onto the live line"
