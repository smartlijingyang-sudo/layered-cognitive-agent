"""ObserverPlugin — metrics + tracing counters per node / edge / subgraph.

Counts every node execution, edge fire, and subgraph enter / exit.
Other observers (Langfuse / OTLP / Prometheus exporters) would subclass
this pattern and replace the storage backend with their real client.

Configuration (``config`` dict):
  metric_prefix : string prefixed to every emitted metric name
                  (default: ``"agent_lab"``).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from agent_lab.plugins.base import (
    GraphPlugin,
    HookContext,
    register_plugin,
)

# Module-level counters — frozen dataclass forbids per-class attribute
# assignment, so we use a module-level dict keyed by plugin ``name``.
# Tests reset this dict via ``ObserverPlugin._reset()``.
_COUNTERS: dict[str, defaultdict[str, int]] = {}


@register_plugin
@dataclass(frozen=True)
class ObserverPlugin(GraphPlugin):
    """Count node / edge / subgraph events; expose counters for tests / metrics."""

    name: str = "default_observer"
    kind: str = "observer"
    binds: tuple = ()
    config: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.name not in _COUNTERS:
            _COUNTERS[self.name] = defaultdict(int)

    @property
    def prefix(self) -> str:
        return str(self.config.get("metric_prefix", "agent_lab"))

    def _bump(self, name: str, count: int = 1) -> None:
        _COUNTERS[self.name][f"{self.prefix}.{name}"] += count

    def on_event(self, ctx: HookContext) -> HookContext:
        kind = ctx.event.value
        if kind == "node_start":
            self._bump("node_start")
        elif kind == "node_end":
            self._bump("node_end.error" if ctx.error else "node_end.ok")
        elif kind == "edge_fire":
            self._bump("edge_fire")
        elif kind == "subgraph_enter":
            self._bump("subgraph_enter")
        elif kind == "subgraph_exit":
            self._bump("subgraph_exit")
        elif kind == "before_compile":
            self._bump("before_compile")
        elif kind == "after_compile":
            self._bump("after_compile")
        return ctx

    @classmethod
    def counters(cls, name: str | None = None) -> dict[str, int]:
        """Return a copy of the metric counters for one plugin (or all).

        ``name`` selects a specific plugin; ``None`` returns the union of
        all plugin counters keyed by metric name (useful for single-plugin
        tests where only one plugin exists).
        """
        if name is None:
            merged: dict[str, int] = {}
            for per_plugin in _COUNTERS.values():
                for k, v in per_plugin.items():
                    merged[k] = merged.get(k, 0) + v
            return merged
        return dict(_COUNTERS.get(name, {}))

    @classmethod
    def _reset(cls, name: str | None = None) -> None:
        """Reset all counters (test-only)."""
        if name is None:
            _COUNTERS.clear()
        else:
            _COUNTERS.pop(name, None)


__all__ = ["ObserverPlugin"]
