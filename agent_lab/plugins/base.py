"""Plugin base — GraphPlugin ABC, PluginRegistry, HookContext, Bind, registry helpers.

The plugin system is the cross-cutting extension point for agent_lab graphs.
Every "横切关注点" (event emission, metrics, control binding, parse rules,
memory policy, stop policy, LLM provider selection, observer metrics) is
expressed as a plugin, NOT as inline code in the runner or in node plugin
files.

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

import dataclasses
import importlib
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

_log = logging.getLogger(__name__)


class HookEvent(StrEnum):
    """Closed set of hook event kinds the runner / compiler emit.

    Semantic events (ON_DECISION / ON_OBSERVATION / ON_REFLECTION) are
    extension points for plugins; the skeleton never maps schema_ref to
    them — a business plugin (e.g. semantic_router) does that.
    """

    # Compile-time hooks (agent_lab.graph.compile)
    BEFORE_COMPILE = "before_compile"
    AFTER_COMPILE = "after_compile"
    # Runtime hooks (agent_lab.runtime.runner)
    NODE_START = "node_start"
    NODE_END = "node_end"
    AFTER_NODE_EXECUTE = "after_node_execute"
    EDGE_FIRE = "edge_fire"
    SUBGRAPH_ENTER = "subgraph_enter"
    SUBGRAPH_EXIT = "subgraph_exit"
    # Semantic hooks — fired by plugins, not by the skeleton
    ON_DECISION = "on_decision"
    ON_OBSERVATION = "on_observation"
    ON_REFLECTION = "on_reflection"
    ON_EVENT = "on_event"


# Compile-time + runtime events; ON_* hooks are opt-in semantic fan-out.
_COMPILE_EVENTS = frozenset({HookEvent.BEFORE_COMPILE, HookEvent.AFTER_COMPILE})
_RUNTIME_EVENTS = frozenset(
    {
        HookEvent.NODE_START,
        HookEvent.NODE_END,
        HookEvent.AFTER_NODE_EXECUTE,
        HookEvent.EDGE_FIRE,
        HookEvent.SUBGRAPH_ENTER,
        HookEvent.SUBGRAPH_EXIT,
    }
)
_SEMANTIC_EVENTS = frozenset(
    {
        HookEvent.ON_DECISION,
        HookEvent.ON_OBSERVATION,
        HookEvent.ON_REFLECTION,
        HookEvent.ON_EVENT,
    }
)


@dataclass(frozen=True, slots=True)
class Bind:
    """A single bind selector narrowing which events a plugin receives."""

    kind: str  # currently only "event_kind"
    value: str

    def __post_init__(self) -> None:
        if self.kind != "event_kind":
            raise ValueError(
                f"Bind.kind must be 'event_kind'; got {self.kind!r}"
            )


@dataclass(frozen=True, slots=True)
class HookContext:
    """Carried payload for every hook invocation.

    The runner builds a HookContext per emitted event; plugins read fields
    and (optionally) replace the value via ``ctx.with_value(...)``.
    """

    event: HookEvent
    spec_id: str = ""
    subgraph_path: str = ""
    node_id: str = ""
    edge_id: str = ""
    node_factory: str = ""
    edge_kind: str = ""
    artifact_digest: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    # Pre-mutation snapshots for before_* hooks
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)

    def with_value(self, **changes: Any) -> HookContext:
        """Return a new HookContext with the given fields replaced.

        Plugins use this in before_* hooks to rewrite inputs / outputs:
            new_ctx = ctx.with_value(inputs=rewritten_inputs)
        The runner picks up the returned value from the plugin and uses it
        for the next stage.
        """
        return dataclasses.replace(self, **changes)


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


# ---------------------------------------------------------------------------
# Plugin registry — classes register via @register_plugin decorator; instances
# bind by id at runtime.
# ---------------------------------------------------------------------------
_PLUGIN_CLASSES: dict[str, type[GraphPlugin]] = {}
_PLUGIN_INSTANCES: dict[str, GraphPlugin] = {}
_FIXTURE_INSTANCES: dict[str, GraphPlugin] = {}


def register_plugin(cls: type[GraphPlugin]) -> type[GraphPlugin]:
    """Class decorator — register a GraphPlugin subclass by ``cls.kind``.

    The plugin's kind (e.g. ``event_sink``) is the lookup key; spec-level
    ``plugins: [{kind: event_sink, ...}]`` references it by kind.
    """
    if not getattr(cls, "kind", None):
        raise ValueError(f"plugin {cls!r} missing 'kind' class attribute")
    if cls.kind in _PLUGIN_CLASSES and _PLUGIN_CLASSES[cls.kind] is not cls:
        raise ValueError(
            f"plugin kind {cls.kind!r} already registered by {_PLUGIN_CLASSES[cls.kind]!r}"
        )
    _PLUGIN_CLASSES[cls.kind] = cls
    return cls


def get_plugin_class(kind: str) -> type[GraphPlugin] | None:
    return _PLUGIN_CLASSES.get(kind)


def register_instance(plugin: GraphPlugin) -> None:
    """Register an instance by name (for spec-level ``id`` binding)."""
    _PLUGIN_INSTANCES[plugin.name] = plugin


def unregister_instance(name: str) -> None:
    _PLUGIN_INSTANCES.pop(name, None)


def get_instance(name: str) -> GraphPlugin | None:
    return _PLUGIN_INSTANCES.get(name)


def register_fixture_instance(name: str, plugin: GraphPlugin) -> None:
    """Test-only — bind a plugin instance by name without going through the class registry."""
    _FIXTURE_INSTANCES[name] = plugin


def unregister_fixture_instance(name: str) -> None:
    _FIXTURE_INSTANCES.pop(name, None)


def get_fixture_instance(name: str) -> GraphPlugin | None:
    return _FIXTURE_INSTANCES.get(name)


def discover() -> dict[str, type[GraphPlugin]]:
    """Import all built-in plugin modules and return the registry.

    Idempotent — call once at runner / compiler init.
    """
    for module_name in (
        "agent_lab.plugins.events",
        "agent_lab.plugins.observers",
        "agent_lab.plugins.parsers",
        "agent_lab.plugins.observation",
        "agent_lab.plugins.memory_extract",
        "agent_lab.plugins.tool_guard",
        "agent_lab.plugins.control_slots",
        "agent_lab.plugins.semantic_router",
    ):
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - import failures
            _log.warning("plugin module %s import failed: %s", module_name, exc)
    return dict(_PLUGIN_CLASSES)


def resolve_plugin(ref: Any) -> GraphPlugin | None:
    """Resolve a PluginRef to a live GraphPlugin instance.

    Resolution order:
      1. fixture registry (test-only; bypasses config)
      2. instance registry by name
      3. instantiate the class with ref.config; register the new instance
    """
    fixture = get_fixture_instance(ref.id)
    if fixture is not None:
        return fixture
    inst = get_instance(ref.id)
    if inst is not None:
        return inst
    cls = get_plugin_class(ref.kind)
    if cls is None:
        _log.warning("plugin kind %r not registered; cannot resolve %r", ref.kind, ref.id)
        return None
    # Instantiate with config
    try:
        inst = cls(
            name=ref.id,
            kind=ref.kind,
            binds=tuple(getattr(ref, "binds", ()) or ()),
            config=dict(getattr(ref, "config", {}) or {}),
        )
    except Exception as exc:  # pragma: no cover - plugin init failures
        _log.warning("plugin %r instantiation failed: %s", ref.id, exc)
        return None
    register_instance(inst)
    return inst


# ---------------------------------------------------------------------------
# Hook dispatcher — fans one event out to every matching plugin.
# ---------------------------------------------------------------------------


def fanout_hooks(
    plugins: list[GraphPlugin],
    event: HookEvent,
    ctx: HookContext,
) -> HookContext:
    """Invoke every plugin whose binds selector matches ``event``.

    Returns the final HookContext (after all plugins mutated it). Plugin
    failures are contained at the per-plugin boundary; an exception in
    one plugin does not stop the others.
    """
    current = ctx
    for plugin in plugins:
        if not plugin.matches(event, current):
            continue
        try:
            current = plugin.dispatch(current)
        except Exception as exc:  # pragma: no cover
            _log.warning("plugin %s dispatch raised: %s", plugin.name, exc)
    return current


__all__ = [
    "Bind",
    "GraphPlugin",
    "HookContext",
    "HookEvent",
    "discover",
    "fanout_hooks",
    "get_fixture_instance",
    "get_instance",
    "get_plugin_class",
    "register_fixture_instance",
    "register_instance",
    "register_plugin",
    "resolve_plugin",
    "unregister_fixture_instance",
    "unregister_instance",
]
