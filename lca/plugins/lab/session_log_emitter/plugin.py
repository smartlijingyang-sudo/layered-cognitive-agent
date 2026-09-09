"""Session log emitter hook plugin for the lab prototype.

Routes framework hook events into the LCA Session via the active
publish session. Self-contained — does NOT import from agent_lab/
(those modules are slated for final deletion per ADR-0209 §6).

History:
- PR-A.3: Copied from agent_lab/nodes/session_log/plugin.py to avoid
  cordis dependency in the test environment.
- PR-D final cleanup: Removed remaining agent_lab imports
  (GraphPlugin, HookContext, session_log._sink) and replaced with
  the lab-internal hooks and a direct Session.append() call via the
  lab.session provider.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from lca.plugins.lab.internal.loader import _LAB_HOOKS
from lca.plugins.lab.internal.hooks import HookContext

_log = logging.getLogger(__name__)

_EVENT_TYPE_MAP: dict[str, str] = {
    "node_start": "graph.node_start.v1",
    "node_end": "graph.node_end.v1",
    "edge_fire": "graph.edge_fire.v1",
    "subgraph_enter": "graph.subgraph_enter.v1",
    "subgraph_exit": "graph.subgraph_exit.v1",
    "before_compile": "graph.before_compile.v1",
    "after_compile": "graph.after_compile.v1",
}


def _current_session():
    """Return the active lab session (set by the session provider at run entry).

    Reads the publish session set by lca.plugins.lab.session.provider.bind_active_session.
    Falls back to a process-global lookup that mirrors the prior agent_lab sink.
    """
    from lca.plugins.events.publishers._session_publish import current_publish_session
    sess = current_publish_session()
    if sess is not None:
        return sess
    # Fallback: process-local noop (allows hook to run before session is bound)
    return _NoopSession()


class _NoopSession:
    """Stand-in for missing session — silently swallows appends."""

    def append(self, event_type: str, payload: Any) -> None:
        _log.debug("session_log_emitter: no session bound, dropping %s", event_type)


@dataclass(frozen=True)
class SessionLogEmitterPlugin:
    """Route framework hooks into the Session.

    This is a hook-only plugin (no Node factory). The runner dispatches
    events via the loader's fanout_hooks path; this class provides the
    hook methods on_event / on_decision / on_observation / on_reflection
    that the dispatcher invokes.
    """

    name: str = "default_session_log_emitter"
    kind: str = "session_log_emitter"
    binds: tuple = ()
    config: dict = field(default_factory=dict)

    def matches(self, event, ctx) -> bool:
        return True  # all events

    def _append(self, event_type: str, ctx: HookContext) -> None:
        try:
            sess = _current_session()
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

    def on_event(self, ctx: HookContext) -> HookContext:
        et = _EVENT_TYPE_MAP.get(ctx.event.value)
        if et is not None:
            self._append(et, ctx)
        return ctx

    def on_decision(self, ctx: HookContext) -> HookContext:
        return ctx

    def on_observation(self, ctx: HookContext) -> HookContext:
        return ctx

    def on_reflection(self, ctx: HookContext) -> HookContext:
        return ctx


_instance = SessionLogEmitterPlugin()
_LAB_HOOKS["lab.hook.session_log_emitter"] = _instance

__all__ = ["SessionLogEmitterPlugin", "_instance"]