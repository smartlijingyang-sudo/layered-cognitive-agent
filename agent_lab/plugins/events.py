"""EventSinkPlugin — single fact-writing surface for graph execution.

Every node/edge/subgraph event during a run is forwarded to a Session
instance via ``LcaEventEmitProvider``. The plugin is the runtime side of
``event_log.yaml`` — the graph surface emits structured events, and this
plugin writes them durably.

Configuration (``config`` dict):
  session_fixture_name : name registered via
                         ``agent_lab.adapters.lca_event.register_fixture_session``.
                         Default fallback: ``_NoopSession`` (records to memory).
  event_types         : tuple of HookEvent values to forward (default: all).
  sink_id             : identifier recorded on every emitted fact
                         (default: plugin name).

Binds default to no filter (all events). Profiles that want to scope to
a phase / node / subgraph pass a ``binds=`` tuple.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from agent_lab.plugins.base import (
    GraphPlugin,
    HookContext,
    register_plugin,
)

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class _InMemorySink:
    """Default fallback when no Session is configured — records events."""

    events: list[dict[str, Any]] = field(default_factory=list)

    def append(self, event_type: str, data: dict[str, Any]) -> Any:  # type: ignore[no-untyped-def]
        record = {"event_type": event_type, "data": data, "sink_id": data.get("sink_id", "")}
        self.events.append(record)
        return record


@register_plugin
@dataclass(frozen=True)
class EventSinkPlugin(GraphPlugin):
    """Forward every graph event to a Session (the LCA fact-write seam)."""

    name: str = "default_event_sink"
    kind: str = "event_sink"
    binds: tuple = ()
    config: dict[str, Any] = field(default_factory=dict)

    def _sink(self):
        """Return the Session (or in-memory fallback) configured by this plugin."""
        # Cache the fallback instance on the plugin so repeated calls
        # share the same event list (important for tests that capture
        # the fallback list reference once and read it later).
        if not hasattr(self, "_fallback_sink"):
            object.__setattr__(self, "_fallback_sink", _InMemorySink())
        session_name = self.config.get("session_fixture_name")
        if session_name:
            try:
                from agent_lab.adapters import lca_event

                sess = getattr(lca_event, "_FIXTURE_SESSIONS", {}).get(session_name)
                if sess is not None:
                    return sess
            except Exception as exc:  # pragma: no cover
                _log.warning(
                    "EventSinkPlugin: fixture session %s not found: %s",
                    session_name,
                    exc,
                )
        return self._fallback_sink

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        sink = self._sink()
        try:
            sink.append(event_type, data)
        except Exception as exc:  # pragma: no cover
            _log.warning("EventSinkPlugin: sink append failed: %s", exc)

    # Hooks — every event we care about goes through on_event; we also
    # tag semantic hooks with their own event_type for downstream consumers.
    def on_event(self, ctx: HookContext) -> HookContext:
        data = {
            "sink_id": self.config.get("sink_id", self.name),
            "event_kind": ctx.event.value,
            "spec_id": ctx.spec_id,
            "subgraph_path": ctx.subgraph_path,
            "node_id": ctx.node_id,
            "node_factory": ctx.node_factory,
            "edge_id": ctx.edge_id,
            "edge_kind": ctx.edge_kind,
            "artifact_digest": ctx.artifact_digest,
            "payload": dict(ctx.payload),
            "error": ctx.error,
        }
        self._emit(f"agent_lab.{ctx.event.value}", data)
        return ctx

    def on_decision(self, ctx: HookContext) -> HookContext:
        return self.on_event(ctx.with_value(payload={**ctx.payload, "kind": "decision"}))

    def on_observation(self, ctx: HookContext) -> HookContext:
        return self.on_event(ctx.with_value(payload={**ctx.payload, "kind": "observation"}))

    def on_reflection(self, ctx: HookContext) -> HookContext:
        return self.on_event(ctx.with_value(payload={**ctx.payload, "kind": "reflection"}))


__all__ = ["EventSinkPlugin", "_InMemorySink"]
