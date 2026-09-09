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


# ---------------------------------------------------------------------------
# ADR-0211 §7:Worker 自动反射 — worker 文件零 framework 知识
#
# 反射规则(只对 ``lca.plugins.lab.act.*`` 生效,本 PR 范围):
#   id          = ``lab.act.<basename>``
#   stage       = 固定 ``"act"``
#   kind        = 模块 docstring 解析 ``kind: TRANSFORMER|EXECUTOR|PROVIDER``
#                 默认 ``TRANSFORMER``
#   node_id     = 模块 basename
#   description = 模块 docstring 第一段(非空行)
#   source_class= basename + "Worker"
#   requires    = ``inspect.signature(worker_fn)`` 的 keyword-only 参数名
#   provides    = ``["lab.act.<basename>.out:<out_port>"]``
#   emits       = 同 provides
#   inputs      = ``[(参数名, type 名, True), ...]``
#   outputs     = ``[(out_port, return_type_name)]``
#   out_capabilities = 同 provides
#
# Worker 函数识别:模块里第一个**非 dataclass / 非 typing 派生**的顶层函数。
# ---------------------------------------------------------------------------

import importlib as _importlib
import inspect as _inspect


def _resolve_worker_fn(module: Any) -> Any:
    """从模块里挑出 worker 主函数。

    规则:
    1. 只看模块**本文件定义**的函数(`module.__dict__` 而非 ``dir(module)``);
       这样不会拿到 ``from .ops import ...`` 引入的同名 helper。
    2. 取本文件定义的第一个 keyword-only def。
    3. 跳过 ``setup`` / ``bind_carrier`` / 任何 ``_*`` 私有 helper。
    """
    SKIP = {"setup", "bind_carrier", "register_worker"}
    candidates: list[Any] = []
    for name, obj in module.__dict__.items():
        if name.startswith("_") or name in SKIP:
            continue
        if not callable(obj):
            continue
        if not _inspect.isfunction(obj):
            continue
        # 必须在本模块定义,非 import
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
        # 多于一个:取名字跟 basename 一致的;否则取第一个 + WARNING 注释。
        basename = module.__name__.split(".")[-1]
        for c in candidates:
            if c.__name__ == basename:
                return c
        return candidates[0]
    return candidates[0]


class WorkerDiscoveryError(Exception):
    """Worker 自动反射失败。worker 文件应符合 §7 反射规则。"""


def _type_name(annotation: Any) -> str:
    """annotation → 简短类型名(用于 marker 的 inputs/outputs kind)。

    ``Artifact | None`` → ``artifact``(unwrap Optional);``list[X]`` → ``list``;
    ``dict[K, V]`` → ``dict``。短路返回简化 marker 可读性。
    """
    import types as _types

    if annotation is _inspect.Parameter.empty or annotation is _inspect.Signature.empty:
        return "any"
    # PEP 604 ``X | Y`` 形式
    if isinstance(annotation, _types.UnionType):
        non_none = [a for a in annotation.__args__ if a is not type(None)]
        if non_none:
            return _type_name(non_none[0])
        return "any"
    # typing.Union[X, Y, ...] 形式
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


def _parse_in_mapping(spec: str) -> dict[str, str]:
    """解析 ``in:`` 行 → ``{param_name: port_name}`` 映射。

    例 ``sensors=sensors_artifact state=state_artifact`` →
    ``{"sensors_artifact": "sensors", "state_artifact": "state"}``。
    解析失败时返回空 dict(让 fallback 用参数名作为 port)。
    """
    if not spec:
        return {}
    out: dict[str, str] = {}
    for tok in spec.split():
        if "=" not in tok:
            continue
        port, _, param = tok.partition("=")
        port = port.strip()
        param = param.strip()
        if port and param:
            out[param] = port
    return out


def _parse_config_params(spec: str) -> set[str]:
    """解析 ``config:`` 行 → ``{param_name}`` 集合。

    例 ``max_chars processor_config`` → ``{"max_chars", "processor_config"}``。
    config 参数**不**进 marker.requires(它们是 graph spec ``node.config``
    静态字段,不是上游 capability key)。
    """
    if not spec:
        return set()
    return {tok.strip() for tok in spec.split() if tok.strip()}


def _parse_docstring_meta(doc: str | None) -> dict[str, str]:
    """从模块 docstring 解析 ``key: value`` 行(只取顶层 meta 行)。"""
    if not doc:
        return {}
    meta: dict[str, str] = {}
    for line in doc.splitlines():
        s = line.strip()
        if not s or ":" not in s:
            continue
        if s.startswith(("---", "===")):
            continue
        k, _, v = s.partition(":")
        meta[k.strip().lower()] = v.strip()
    return meta


def discover_worker(module_path: str) -> tuple[LabCarrier, Any, tuple[str, ...]]:
    """反射一个 stage worker 模块,返回 ``(LabCarrier, worker_fn, config_params)``。

    worker 文件**零 framework 知识**;所有元数据由本函数从代码 + docstring 派生。
    stage 由 module_path 推导(perceive / think / act / reflect / remember / ...)。
    """
    module = _importlib.import_module(module_path)
    worker_fn = _resolve_worker_fn(module)
    sig = _inspect.signature(worker_fn)

    # 派生 id / stage / node_id
    # module_path 形式: ``lca.plugins.lab.<stage>.<basename>[.plugin]``
    parts = module_path.split(".")
    basename = parts[-2] if parts[-1] == "plugin" else parts[-1]
    # stage: ``lca.plugins.lab.<stage>...`` → parts[3]
    if len(parts) >= 4 and parts[1] == "plugins" and parts[2] == "lab":
        stage = parts[3]
    else:
        stage = "unknown"
    cid = f"lab.{stage}.{basename}"
    node_id = basename

    # 派生 kind / description 从 docstring
    meta = _parse_docstring_meta(module.__doc__)
    kind = meta.get("kind", "TRANSFORMER").upper()
    description = meta.get("description") or (
        module.__doc__.splitlines()[0].strip() if module.__doc__ else cid
    )

    # 派生 requires / inputs from signature + docstring ``in:`` 端口映射
    # + ``config:`` 静态 config 参数(不进 requires,只走 inputs)
    #
    # docstring 形如:
    #   in: <port_name>=<param_name> [<port_name>=<param_name> ...]
    #   config: <param_name> [<param_name> ...]
    # 例如:
    #   in: sensors=sensors_artifact state=state_artifact
    #   config: max_chars
    # config 参数从 graph spec 的 ``node.config`` 字段读,**不**进 ``requires``(不进
    # requires 表示它不是上游产物的 capability key),但仍出现在 ``inputs`` 用于校验。
    # 若 docstring 没有 ``in:`` 行,fallback 用参数名作为 port 名。
    in_mapping = _parse_in_mapping(meta.get("in", ""))
    config_params = _parse_config_params(meta.get("config", ""))
    requires: list[str] = []
    inputs: list[tuple[str, str, bool]] = []
    for pname, param in sig.parameters.items():
        if param.kind is _inspect.Parameter.KEYWORD_ONLY:
            port_name = in_mapping.get(pname, pname)
            if pname not in config_params:
                requires.append(port_name)
            inputs.append((port_name, _type_name(param.annotation), True))

    # 派生 provides / outputs from return annotation
    out_port = meta.get("out_port", "out")
    out_type = _type_name(sig.return_annotation)
    provides = (f"{cid}.out:{out_port}",)
    outputs = ((out_port, out_type),)

    carrier = LabCarrier(
        id=cid,
        stage=stage,
        kind=kind,
        description=description,
        node_id=node_id,
        source_module=module_path,
        source_class=f"{node_id}Worker",
        provides=provides,
        requires=tuple(requires),
        emits=provides,
        inputs=tuple(inputs),
        outputs=outputs,
        out_capabilities=provides,
    )
    return carrier, worker_fn, tuple(sorted(config_params))


def bind_worker(module_path: str, *, ctx: Any = None, config: Any = None) -> None:
    """反射一个 stage worker 模块并 bind_carrier(框架入口,worker 文件不调)。

    替代 worker 文件里手写的 ``_CARRIER = LabCarrier(...)`` + ``bind_carrier(_CARRIER)``。
    stage 由 module_path 推导(perceive / think / act / reflect / remember)。
    把 worker_fn + config_params + port_to_param 一起写入 marker;invoke 调
    ``marker["worker_fn"](**mapped_inputs)``。
    """
    carrier, worker_fn, config_params = discover_worker(module_path)
    bind_carrier(carrier, ctx=ctx, config=config)
    from lca.plugins.lab.internal.loader import _LAB_HOOKS

    marker = _LAB_HOOKS[carrier.id]
    marker["worker_fn"] = worker_fn
    marker["config_params"] = list(config_params)
    # ADR-0211 §7:存 port→param 映射,invoke 用它把 inputs(port 名) 重写为
    # worker_fn 的 keyword-only 参数名。
    module = _importlib.import_module(module_path)
    meta = _parse_docstring_meta(module.__doc__ or "")
    in_mapping = _parse_in_mapping(meta.get("in", ""))
    # in_mapping: {param_name: port_name} → 反转成 {port_name: param_name}
    marker["port_to_param"] = {port: param for param, port in in_mapping.items()}


# 旧名 alias —— 保留以兼容 PR-D final 2/2 期间可能残留的引用。
discover_act_worker = discover_worker
bind_act_worker = bind_worker


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
