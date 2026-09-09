"""Internal hook helper for lab plugins.

PR-A.2 — hook helper 私有化；本模块仅供 lca.plugins.lab.* plugin 与
agent_lab graph/compile / runtime/runner 在过渡期使用；PR-A.3 后
graph/compile.py / runtime/runner.py 改用 lca.plugins.lab.internal.hooks。

Exposes the closed set of compile-time / runtime hook kinds (HookEvent),
the per-event payload (HookContext), the bind selector (Bind) and the
fan-out dispatcher (fanout_hooks). The semantics are unchanged from the
original ``agent_lab.plugins.base`` module — only the import path moved
into the LCA plugin tree.
"""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

_log = logging.getLogger(__name__)


class Worker:
    """Cordis-free Worker base class for backward compat with legacy plugin classes.

    ADR-0211 §6 §1:``Worker`` 类从 ``lca.plugins.lab.internal.worker``
    移到本模块(``hooks.py``);register_worker / lookup_worker 等旧入口
    同 PR 退役。新插件用 ``bind_carrier(LabCarrier(...))`` 模式,不需要
    继承 Worker。
    """

    factory: str = ""

    def execute(self, node: Any, inputs: Any, seams: Any = None) -> dict:
        raise NotImplementedError(self.factory or type(self).__name__)


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


# ---------------------------------------------------------------------------
# Hook dispatcher — fans one event out to every matching plugin.
# ---------------------------------------------------------------------------


def fanout_hooks(
    plugins: list[Any],
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
    "HookContext",
    "HookEvent",
    "fanout_hooks",
]


# ---------------------------------------------------------------------------
# PR-D final 2/2 — LabCarrier + bind_carrier
#
# A cordis-free mirror of the LCA @plugin carrier data model. The full
# ``lca.harness.plugin_api`` path requires `cordis.plugin` (not available
# in the test environment), so we re-declare the data shape the loader
# needs and re-export it under the lab plugin tree.
# ---------------------------------------------------------------------------

from typing import Any, Callable


@dataclass(frozen=True)
class LabCarrier:
    """Pydantic-free mirror of the LCA @plugin carrier shape.

    Carries everything the loader's ``register_carrier`` needs to populate
    `_LAB_HOOKS` and to satisfy the capability closed-set spec.

    Fields:
        id:              carrier slot id (e.g. ``lab.perceive.sense``)
        stage:           process / phase (perceive / think / act / ...)
        kind:            NodeKind equivalent (TRANSFORMER / EXECUTOR / ...)
        description:     human-readable
        node_id:         the agent_lab node factory id (matches basename)
        source_module:   module path that owns the legacy class
        source_class:    legacy class name (lazy-imported at runtime)
        provides:        capability keys the node contributes
        requires:        capability keys the node consumes
        emits:           event-class / artefact-class names the node emits
        inputs:          port spec (port_id, port_kind, required)
        outputs:         port spec (port_id, port_kind)
        out_capabilities: out:<port> capability keys (for closure spec)
    """
    id: str
    stage: str
    kind: str
    description: str
    node_id: str
    source_module: str
    source_class: str
    provides: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    emits: tuple[str, ...] = ()
    inputs: tuple[tuple[str, str, bool], ...] = ()   # (port, kind, required)
    outputs: tuple[tuple[str, str], ...] = ()         # (port, kind)
    out_capabilities: tuple[str, ...] = ()


def _factory_aliases(carrier: LabCarrier) -> tuple[str, ...]:
    """YAML factory keys plus carrier.id. Order is stable; duplicates dropped."""
    raw = [carrier.id]
    if carrier.id.startswith("lab."):
        raw.append(carrier.id[4:])
    raw.append(carrier.id.rsplit(".", 1)[-1])
    if carrier.node_id:
        raw.append(carrier.node_id)
    seen: set[str] = set()
    out: list[str] = []
    for alias in raw:
        if alias and alias not in seen:
            seen.add(alias)
            out.append(alias)
    return tuple(out)


# ADR-0211 §6 §1:``_ALIASES`` / ``lookup_alias`` 取代 worker.py 的
# ``_ALIAS_TO_CANONICAL`` / ``lookup_worker``。本字典记录 carrier_id →
# factory alias tuple,让 runner 通过短名("shape")查长名("lab.act.shape")。
_ALIASES: dict[str, tuple[str, ...]] = {}


def lookup_alias(alias: str) -> str | None:
    """给定 factory alias,返回对应的 canonical carrier id;None 表示没找到。"""
    from lca.plugins.lab.internal.loader import _LAB_HOOKS

    if alias in _LAB_HOOKS:
        return alias
    for canonical, aliases in _ALIASES.items():
        if alias in aliases:
            return canonical
    return None


# 保留旧函数名以兼容 agent_lab.runtime.invoke 引用;
# ADR-0211 §6 §1 完整退役时一并改名 / 删除。


def bind_carrier(carrier: LabCarrier, *, ctx: Any = None, config: Any = None) -> None:
    """Register a LabCarrier with the loader's _LAB_HOOKS.

    The real @plugin decorator builds a PluginDefinition and registers
    it with Cordis. This function does the same end state for the lab
    plugin tree without the cordis dependency.

    The marker stored in _LAB_HOOKS is the dict the runner reads when
    resolving a node factory. Factory aliases are recorded so invoke
    can resolve YAML keys (``perceive.sense``, ``expose_schemas``).
    """
    del ctx, config
    from lca.plugins.lab.internal.loader import _LAB_HOOKS  # local import

    aliases = _factory_aliases(carrier)
    marker = {
        "id": carrier.node_id,
        "stage": carrier.stage,
        "kind": carrier.kind,
        "module": carrier.source_module,
        "class": carrier.source_class,
        "provides": list(carrier.provides),
        "requires": list(carrier.requires),
        # ADR-0211 §3 W-2: ``needs`` is the legacy alias kept for the
        # PR-B act.* test suite; canonical name is ``requires``.
        "needs": list(carrier.requires),
        "emits": list(carrier.emits),
        "inputs": [
            {"port": p, "kind": k, "required": r}
            for (p, k, r) in carrier.inputs
        ],
        "outputs": [{"port": p, "kind": k} for (p, k) in carrier.outputs],
        "out_capabilities": list(carrier.out_capabilities),
        "description": carrier.description,
        "carrier_id": carrier.id,
        "factory_aliases": list(aliases),
    }
    _LAB_HOOKS[carrier.id] = marker
    # ADR-0211 §6 §1:``bind_factory_aliases`` / ``_WORKERS`` 退役;
    # alias 解析由 hooks.py 自己的 _ALIASES 承担,不动 worker.py。
    _ALIASES[carrier.id] = aliases  # noqa: F821 (defined in this module above)


__all__ += ["LabCarrier", "bind_carrier"]


# ---------------------------------------------------------------------------
# PR-D final cleanup — GraphPlugin (data class only, no register surface)
#
# This is the cordis-free mirror of agent_lab.plugins.base.GraphPlugin.
# It provides the @dataclass hook methods the runner's fanout_hooks
# dispatcher invokes. No `register` / `discover` / `resolve` surface —
# the new loader path is lca.plugins.lab.internal.loader.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GraphPlugin:
    """Base dataclass for hook-bearing plugins.

    Subclass and override the hook methods you care about
    (before_compile / after_compile / on_event / on_decision /
    on_observation / on_reflection). The runner's fanout_hooks
    dispatcher calls these via ``dispatch(ctx)``.

    Fields:
        name:     unique id within the loader's _LAB_HOOKS
        kind:     plugin kind (e.g. ``event_sink``, ``observer``)
        binds:    event selector; empty tuple means match-all
        config:   yaml-level configuration block
    """

    name: str
    kind: str
    binds: tuple["Bind", ...] = ()
    config: dict[str, Any] = field(default_factory=dict)

    def matches(self, event: "HookEvent", ctx: "HookContext") -> bool:
        if not self.binds:
            return True
        for bind in self.binds:
            if (bind.kind == "event_kind"
                    and bind.value != "*"
                    and bind.value != event.value):
                return False
        return True

    def dispatch(self, ctx: "HookContext") -> "HookContext":
        if not self.matches(ctx.event, ctx):
            return ctx
        method = getattr(self, ctx.event.value, None)
        if method is None:
            method = getattr(self, "on_event", None)
        if method is None:
            return ctx
        try:
            return method(ctx)
        except Exception as exc:  # containment boundary
            _log.warning("plugin %s hook %s raised: %s", self.name, ctx.event.value, exc)
            return ctx

    def before_compile(self, spec: Any, sub_registry: Any = None) -> Any:
        """No-op: plugins must not rewrite topology. Return spec unchanged."""
        del sub_registry
        return spec

    # Default hook methods (no-op). Override in subclasses.
    def on_decision(self, ctx: "HookContext") -> "HookContext":
        return ctx

    def on_observation(self, ctx: "HookContext") -> "HookContext":
        return ctx

    def on_reflection(self, ctx: "HookContext") -> "HookContext":
        return ctx

    def on_event(self, ctx: "HookContext") -> "HookContext":
        return ctx


__all__ += ["GraphPlugin"]
