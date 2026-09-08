# PR-A.3 — simplified plugin that doesn't depend on LCA plugin system
"""Session log emitter hook plugin for agent_lab prototype.

Copied from agent_lab/nodes/session_log/plugin.py to avoid cordis dependency
in test environment. This plugin routes hook events to the session log.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from lca.plugins.lab.internal.loader import _LAB_HOOKS
from agent_lab.plugins.base import GraphPlugin, HookContext

_log = logging.getLogger(__name__)

# Mapping: HookEvent -> (event_type_str, input_port_id_for_session_log_node)
_EVENT_TYPE_MAP: dict[str, str] = {
    "node_start": "graph.node_start.v1",
    "node_end": "graph.node_end.v1",
    "edge_fire": "graph.edge_fire.v1",
    "subgraph_enter": "graph.subgraph_enter.v1",
    "subgraph_exit": "graph.subgraph_exit.v1",
    "before_compile": "graph.before_compile.v1",
    "after_compile": "graph.after_compile.v1",
}


@dataclass(frozen=True)
class SessionLogEmitterPlugin(GraphPlugin):
    """Route framework hooks into the Session via session_log._sink."""

    name: str = "default_session_log_emitter"
    kind: str = "session_log_emitter"
    binds: tuple = ()
    config: dict = field(default_factory=dict)

    def _append(self, event_type: str, ctx: HookContext) -> None:
        try:
            from agent_lab.nodes.session_log._sink import get_session

            sess = get_session()
            # Build a compact event payload mirroring the trace event
            payload = {
                "kind": ctx.event.value,
                "subgraph_path": ctx.subgraph_path,
                "node_id": ctx.node_id,
                "node_full_path": (
                    f"{ctx.subgraph_path}/{ctx.node_id}"
                    if ctx.node_id
                    else (ctx.subgraph_path or "")
                ),
                "edge_id": ctx.edge_id,
                "edge_kind": ctx.edge_kind,
                "node_factory": ctx.node_factory,
                "artifact_digest": ctx.artifact_digest,
                **dict(ctx.payload or {}),
            }
            sess.append(event_type, payload)
        except Exception as exc:  # containment boundary
            _log.debug("SessionLogEmitterPlugin append %s failed: %s", event_type, exc)

    # Hook handlers — call sess.append for each event type.
    def on_event(self, ctx: HookContext) -> HookContext:
        et = _EVENT_TYPE_MAP.get(ctx.event.value)
        if et is not None:
            self._append(et, ctx)
        return ctx

    # Aliases — the plugin dispatcher calls hooks by event value.
    def on_decision(self, ctx: HookContext) -> HookContext:
        # Domain facts are still routed to the Session (separable hook).
        return ctx

    def on_observation(self, ctx: HookContext) -> HookContext:
        return ctx

    def on_reflection(self, ctx: HookContext) -> HookContext:
        return ctx


# Populate at import time for load_all()
_instance = SessionLogEmitterPlugin()
_LAB_HOOKS["lab.hook.session_log_emitter"] = _instance

__all__ = ["SessionLogEmitterPlugin", "_instance"]
