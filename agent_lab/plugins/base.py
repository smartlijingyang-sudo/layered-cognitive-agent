"""Plugin base — GraphPlugin ABC and hook helper re-exports.

The plugin system is the cross-cutting extension point for agent_lab graphs.
Every "横切关注点" (event emission, metrics, control binding, parse rules,
memory policy, stop policy, LLM provider selection, observer metrics) is
expressed as a plugin, NOT as inline code in the runner or in node plugin
files.

PR-A.3 status:
  The plugin registration surface (register_plugin, discover, resolve_plugin,
  etc.) has been removed. Plugin resolution now uses lca.plugins.lab.internal.loader.
  The GraphPlugin base class remains as a marker interface for handlers that
  support hook methods.

Hook helpers (HookEvent, HookContext, Bind, fanout_hooks) are re-exported
from lca.plugins.lab.internal.hooks for backwards compatibility.

Each plugin declares which hooks it cares about by overriding the
relevant hook methods (before_compile / after_compile / before_node_execute
/ after_node_execute / before_edge_fire / after_edge_fire / before_subgraph_enter
/ after_subgraph_exit / on_event / on_decision / on_observation / on_reflection).
The runner calls each matching hook method at the right point; failures are
contained at the runner boundary (mirrors LCA Session observer containment).

Bind selectors narrow which events a plugin receives:
  Bind(kind="phase",       value="think")     # only think-phase events
  Bind(kind="node",        value="call_llm")   # only the call_llm node
  Bind(kind="edge",        value="*")          # all edges
  Bind(kind="subgraph",    value="*")          # all subgraphs
  Bind(kind="event_kind",  value="node_start") # only node_start events

An empty binds tuple means "match everything".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from lca.plugins.lab.internal.hooks import Bind, HookContext, HookEvent, fanout_hooks

_log = logging.getLogger(__name__)

__all__ = [
    "Bind",
    "GraphPlugin",
    "HookContext",
    "HookEvent",
    "fanout_hooks",
    "register_plugin",  # Backwards compatibility
]


@dataclass(frozen=True)
class GraphPlugin:
    """Base class every plugin inherits from.

    Subclass and override the hook methods you care about. The ``name``
    and ``kind`` fields are mandatory; ``binds`` is optional (empty means
    match all events). ``config`` carries the yaml-level configuration
    block.
    """

    name: str
    kind: str
    binds: tuple[Bind, ...] = ()
    config: dict[str, Any] = field(default_factory=dict)

    def matches(self, event: HookEvent, ctx: HookContext) -> bool:
        """Return True iff this plugin should receive this event."""
        if not self.binds:
            return True
        for bind in self.binds:
            if bind.kind == "event_kind" and bind.value != "*" and bind.value != event.value:
                return False
        return True

    # Hooks — default no-op. Override as needed.
    def before_compile(
        self, spec: Any, sub_registry: dict[str, Any] | None = None
    ) -> Any:  # type: ignore[no-untyped-def]
        return spec

    def after_compile(self, bundle: Any) -> Any:  # type: ignore[no-untyped-def]
        return bundle

    def on_decision(self, ctx: HookContext) -> HookContext:
        return ctx

    def on_observation(self, ctx: HookContext) -> HookContext:
        return ctx

    def on_reflection(self, ctx: HookContext) -> HookContext:
        return ctx

    def on_event(self, ctx: HookContext) -> HookContext:
        return ctx

    # Dispatcher: routes a HookContext to the right hook method.
    #
    # Resolution order:
    #   1. Bind selectors gate whether the plugin receives the event
    #   2. The kind-specific method (``on_decision`` for ON_DECISION, etc.)
    #   3. The generic ``on_event`` catch-all
    def dispatch(self, ctx: HookContext) -> HookContext:
        if not self.matches(ctx.event, ctx):
            return ctx
        method = getattr(self, ctx.event.value, None)
        if method is None:
            method = getattr(self, "on_event", None)
        if method is None:
            return ctx
        try:
            return method(ctx)
        except Exception as exc:  # containment boundary (mirrors LCA Session observers)
            _log.warning("plugin %s hook %s raised: %s", self.name, ctx.event.value, exc)
            return ctx


# Backwards compatibility: keep register_plugin as a no-op decorator
# so old agent_lab plugins can still use it during the transition.
# The new loader path (lca.plugins.lab.internal.loader) doesn't use this.
def register_plugin(cls):
    """No-op decorator for backwards compatibility.
    
    Old agent_lab plugins use @register_plugin but the new loader path
    doesn't need it. This is kept to avoid breaking existing code during
    the transition period.
    """
    return cls
