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
    "GraphPlugin",
    "HookContext",
    "HookEvent",
    "Worker",
    "fanout_hooks",
]


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
    binds: tuple[Bind, ...] = ()
    config: dict[str, Any] = field(default_factory=dict)

    def matches(self, event: HookEvent, ctx: HookContext) -> bool:
        if not self.binds:
            return True
        for bind in self.binds:
            if (bind.kind == "event_kind"
                    and bind.value != "*"
                    and bind.value != event.value):
                return False
        return True

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
        except Exception as exc:  # containment boundary
            _log.warning("plugin %s hook %s raised: %s", self.name, ctx.event.value, exc)
            return ctx

    def before_compile(self, spec: Any, sub_registry: Any = None) -> Any:
        """No-op: plugins must not rewrite topology. Return spec unchanged."""
        del sub_registry
        return spec

    # Default hook methods (no-op). Override in subclasses.
    def on_decision(self, ctx: HookContext) -> HookContext:
        return ctx

    def on_observation(self, ctx: HookContext) -> HookContext:
        return ctx

    def on_reflection(self, ctx: HookContext) -> HookContext:
        return ctx

    def on_event(self, ctx: HookContext) -> HookContext:
        return ctx


# ---------------------------------------------------------------------------
# Worker discovery — register a stage worker's marker into _LAB_HOOKS by
# reflecting its module. The carrier dataclass was removed in PR-D final 2/2
# retirement; marker is now a plain dict shaped for the runner / invoke.
# ---------------------------------------------------------------------------

import importlib as _importlib
import inspect as _inspect
import types as _types


class WorkerDiscoveryError(Exception):
    """Worker reflection failed; worker must define a keyword-only function."""


def _type_name(annotation: Any) -> str:
    import types as _types

    if annotation is _inspect.Parameter.empty or annotation is _inspect.Signature.empty:
        return "any"
    if isinstance(annotation, _types.UnionType):
        non_none = [a for a in annotation.__args__ if a is not type(None)]
        if non_none:
            return _type_name(non_none[0])
        return "any"
    origin = getattr(annotation, "__origin__", None)
    args = getattr(annotation, "__args__", None)
    if origin is not None and args is not None:
        non_none = [a for a in args if a is not type(None)]
        if non_none:
            return _type_name(non_none[0])
        return "any"
    name = getattr(annotation, "__name__", None)
    if name is not None:
        return name.lower()
    return str(annotation).lower()


def _parse_docstring_meta(doc: str | None) -> dict[str, str]:
    if not doc:
        return {}
    meta: dict[str, str] = {}
    for line in doc.splitlines():
        s = line.strip()
        if not s or ":" not in s:
            continue
        if s.startswith(("#", "---", "===")):
            continue
        k, _, v = s.partition(":")
        meta[k.strip().lower()] = v.strip()
    return meta


def _resolve_worker_fn(module: Any) -> Any:
    """Pick the worker fn from a stage plugin module.

    Same rules as before (first keyword-only def defined in this module),
    but the SKIP set no longer mentions ``bind_carrier`` (gone).
    """
    SKIP = {"setup"}
    candidates: list[Any] = []
    for name, obj in module.__dict__.items():
        if name.startswith("_") or name in SKIP:
            continue
        if not callable(obj) or not _inspect.isfunction(obj):
            continue
        if getattr(obj, "__module__", None) != module.__name__:
            continue
        sig = _inspect.signature(obj)
        if not any(
            p.kind is _inspect.Parameter.KEYWORD_ONLY
            for p in sig.parameters.values()
        ):
            continue
        candidates.append(obj)
    if not candidates:
        raise WorkerDiscoveryError(
            f"{module.__name__}: no keyword-only function defined in this module; "
            "worker must define `def name(*, ...)` directly in plugin.py"
        )
    if len(candidates) > 1:
        basename = module.__name__.split(".")[-1]
        for c in candidates:
            if c.__name__ == basename:
                return c
        return candidates[0]
    return candidates[0]


def discover_worker(module_path: str) -> tuple[dict, Any, tuple[str, ...]]:
    """Reflect a stage worker module → ``(marker_dict, worker_fn, config_params)``.

    ``marker_dict`` carries id / stage / kind / provides / requires / inputs /
    outputs — same shape as the legacy carrier, but a plain ``dict`` for
    readability. The loader's ``bind_worker`` writes this into ``_LAB_HOOKS``.
    """
    module = _importlib.import_module(module_path)
    worker_fn = _resolve_worker_fn(module)
    sig = _inspect.signature(worker_fn)

    parts = module_path.split(".")
    basename = parts[-2] if parts[-1] == "plugin" else parts[-1]
    if len(parts) >= 4 and parts[1] == "plugins" and parts[2] == "lab":
        stage = parts[3]
    else:
        stage = "unknown"
    cid = f"lab.{stage}.{basename}"

    meta = _parse_docstring_meta(module.__doc__)
    kind = meta.get("kind", "TRANSFORMER").upper()
    description = meta.get("description") or (
        module.__doc__.splitlines()[0].strip() if module.__doc__ else cid
    )
    out_port = meta.get("out_port", "out")
    out_type = _type_name(sig.return_annotation)
    provides = (f"{cid}.out:{out_port}",)
    outputs = ((out_port, out_type),)
    requires: list[str] = []
    inputs: list[tuple[str, str, bool]] = []
    for pname, param in sig.parameters.items():
        if param.kind is _inspect.Parameter.KEYWORD_ONLY:
            requires.append(pname)
            inputs.append((pname, _type_name(param.annotation), True))
    config_params = tuple(
        tok.strip() for tok in meta.get("config", "").split() if tok.strip()
    )

    marker = {
        "id": cid,
        "stage": stage,
        "kind": kind,
        "description": description,
        "module": module_path,
        "class": f"{basename}Worker",
        "provides": list(provides),
        "requires": requires,
        "inputs": [
            {"port": p, "kind": k, "required": r} for (p, k, r) in inputs
        ],
        "outputs": [{"port": p, "kind": k} for (p, k) in outputs],
        "out_capabilities": list(provides),
        "factory_aliases": [basename],
    }

    from lca.plugins.lab.internal.audit import (
        WorkerAuditFailure,
        audit_worker,
    )

    audit_errors = audit_worker(module_path, worker_fn)
    if audit_errors:
        raise WorkerAuditFailure(audit_errors, module_path=module_path)

    return marker, worker_fn, config_params


def bind_worker(module_path: str, *, ctx: Any = None, config: Any = None) -> None:
    """Reflect a stage worker module and register its marker into ``_LAB_HOOKS``.

    Provider-form plugins (``provider: yes`` in docstring) opt out and keep
    their hand-rolled registration path.
    """
    del ctx, config
    from lca.plugins.lab.internal.loader import _LAB_HOOKS

    marker, worker_fn, config_params = discover_worker(module_path)
    marker["worker_fn"] = worker_fn
    marker["config_params"] = list(config_params)
    _LAB_HOOKS[marker["id"]] = marker


__all__ += ["WorkerDiscoveryError", "bind_worker", "discover_worker"]
