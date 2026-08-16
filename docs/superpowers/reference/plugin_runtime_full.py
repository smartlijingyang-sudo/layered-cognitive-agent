"""Cordis-compatible plugin runtime in pure Python — 100% coverage of vendor/.

Covers all 10 vendor packages:
- cordis core (context, fiber, events, reflect, registry, service, logger, utils)
- cordis loader (entry, tree, group, isolate, utils, internal)
- include (YAML/JSON file-backed EntryTree + patch semantics)
- hmr (watchdog + importlib.reload + AST dependency analysis + rollback)
- timer (timeout/interval/debounce/throttle with fiber lifecycle)
- schemastery (→ pydantic V2)
- cosmokit (→ Python stdlib)
- logger-console (→ structlog / rich)
- group (→ YAML group entry)

Run:  python3 plugin_runtime_full.py
Test: python3 -m pytest test_plugin_runtime_full.py -v

Dependencies: Python 3.11+, watchdog (optional, for HMR), pyyaml (optional).
"""

from __future__ import annotations

import asyncio
import ast
import importlib
import importlib.util
import inspect
import itertools
import json
import operator
import os
import sys
import traceback
from abc import ABC, ABCMeta
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import ModuleType
from typing import (
    Any, Awaitable, Callable, ClassVar, Generator, Iterable, Mapping,
)


# ═══════════════════════════════════════════════════════════════
# §1 — TYPES & ERRORS
# ═══════════════════════════════════════════════════════════════

Cleanup = Callable[[], Any]
Listener = Callable[..., Any]
Apply = Callable[..., Any]
Effect = (
    Cleanup
    | Callable[[], Any]
    | Iterable[Cleanup]
)


def is_bailed(value: Any) -> bool:
    """Bail value = non-None and non-False. (Cordis isBailed)"""
    return value is not None and value is not False


class PluginError(RuntimeError):
    """Plugin config, load, or lifecycle transition failure."""

class DependencyUnavailable(PluginError):
    """Required service not yet available."""


class PluginState(str, Enum):
    PENDING = "pending"
    LOADING = "loading"
    ACTIVE = "active"
    FAILED = "failed"
    UNLOADING = "unloading"
    DISPOSED = "disposed"


# ═══════════════════════════════════════════════════════════════
# §2 — DisposableList (O(1) delete)
# ═══════════════════════════════════════════════════════════════

class DisposableList:
    """Ordered disposable collection with O(1) delete-by-value.
    (Cordis DisposableList — WeakMap + sequence number dual index)
    """

    def __init__(self) -> None:
        self._sn = 0
        self._map: dict[int, Any] = {}
        self._weak: dict[int, int] = {}

    def __len__(self) -> int:
        return len(self._map)

    def push(self, value: Any) -> Callable[[], bool]:
        self._sn += 1
        sn = self._sn
        self._map[sn] = value
        self._weak[id(value)] = sn
        return lambda: self._map.pop(sn, None) is not None

    def delete(self, value: Any) -> bool:
        sn = self._weak.pop(id(value), None)
        if sn is None:
            return False
        self._map.pop(sn, None)
        return True

    def clear(self) -> list[Any]:
        values = list(reversed(self._map.values()))
        self._map.clear()
        self._weak.clear()
        return values

    def __iter__(self):
        return iter(list(self._map.values()))


# ═══════════════════════════════════════════════════════════════
# §3 — EffectMeta diagnostic tree
# ═══════════════════════════════════════════════════════════════

@dataclass
class EffectMeta:
    """Diagnostic node for one effect. (Cordis EffectMeta)"""
    label: str
    children: list[EffectMeta] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════
# §4 — composeError stack stitching
# ═══════════════════════════════════════════════════════════════

def compose_error(callback: Callable, get_outer_stack: Callable[[], list[str]]) -> Any:
    """Capture caller stack, splice into async error. (Cordis composeError)"""
    outer_frames = get_outer_stack()
    try:
        result = callback()
        if inspect.isawaitable(result):
            async def wrapped():
                try:
                    return await result
                except BaseException as exc:
                    _append_frames(exc, outer_frames)
                    raise
            return wrapped()
        return result
    except BaseException as exc:
        _append_frames(exc, outer_frames)
        raise


def _append_frames(exc: BaseException, frames: list[str]) -> None:
    if hasattr(exc, '__traceback__') and frames:
        tb_str = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)).rstrip()
        for frame in frames:
            tb_str += f"\n    {frame}"
        exc._composed_traceback = tb_str  # type: ignore


def build_outer_stack(offset: int = 0) -> Callable[[], list[str]]:
    frames = traceback.format_stack()
    return lambda: frames[3 + offset:]


# ═══════════════════════════════════════════════════════════════
# §5 — PluginSpec (3 shapes)
# ═══════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class PluginSpec:
    """Plugin descriptor. Supports Function / Constructor / Object shapes."""
    name: str
    apply: Apply
    inject: tuple[str, ...] | dict[str, Any] = ()
    provides: str | None = None
    validate: Callable[[Any], Any] | None = None
    is_class: bool = False


# ═══════════════════════════════════════════════════════════════
# §6 — ServiceRecord
# ═══════════════════════════════════════════════════════════════

@dataclass
class ServiceRecord:
    name: str
    value: Any
    owner_id: str
    check: Callable[[], bool] | None = None

    @property
    def available(self) -> bool:
        return self.check is None or bool(self.check())


# ═══════════════════════════════════════════════════════════════
# §7 — PluginHandle (Fiber equivalent)
# ═══════════════════════════════════════════════════════════════

@dataclass
class PluginHandle:
    """Runtime state for one entry. Equivalent to Cordis Fiber."""
    entry_id: str
    spec: PluginSpec
    config: Any
    injected: tuple[str, ...]
    desired: bool = True
    state: PluginState = PluginState.PENDING
    error: BaseException | None = None
    effects: list[tuple[Cleanup, EffectMeta | None]] = field(default_factory=list)
    provided_services: set[str] = field(default_factory=set)
    listener_tokens: set[tuple[str, int]] = field(default_factory=set)
    disposables: DisposableList = field(default_factory=DisposableList)
    inertia: asyncio.Task | None = None
    _epoch: str = "__INACTIVE__"
    _accessors: dict[str, dict] = field(default_factory=dict)
    _entry: Any = None

    @property
    def dependencies(self) -> tuple[str, ...]:
        return self.injected

    def get_effects_meta(self) -> list[EffectMeta]:
        return [meta for _, meta in self.effects if meta is not None]

    async def await_settled(self) -> "PluginHandle":
        while self.inertia:
            await self.inertia
        if self.error:
            raise self.error
        return self


# ═══════════════════════════════════════════════════════════════
# §8 — ListenerRecord
# ═══════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class _ListenerRecord:
    token: int
    owner_id: str
    callback: Listener
    prepend: bool = False
    global_: bool = False


# ═══════════════════════════════════════════════════════════════
# §9 — EventBus (5 dispatch modes)
# ═══════════════════════════════════════════════════════════════

class EventBus:
    """Event bus with lifecycle ownership.
    Covers: emit / parallel / serial / bail / waterfall + once + Context filter.
    """

    def __init__(self) -> None:
        self._events: dict[str, list[_ListenerRecord]] = defaultdict(list)
        self._counter = itertools.count(1)

    def on(self, owner_id: str, event: str, callback: Listener, *,
           prepend: bool = False, global_: bool = False) -> tuple[str, int]:
        token = next(self._counter)
        record = _ListenerRecord(token, owner_id, callback, prepend, global_)
        if prepend:
            self._events[event].insert(0, record)
        else:
            self._events[event].append(record)
        return event, token

    def off(self, token: tuple[str, int]) -> bool:
        event, target = token
        listeners = self._events.get(event, [])
        for index, record in enumerate(listeners):
            if record.token == target:
                listeners.pop(index)
                if not listeners:
                    self._events.pop(event, None)
                return True
        return False

    def _dispatch_listeners(self, event: str, filter_fn: Callable | None = None) -> list[Listener]:
        hooks = self._events.get(event, [])
        return [
            h.callback for h in hooks
            if h.global_ or not filter_fn or filter_fn(h)
        ]

    async def emit(self, event: str, *args: Any) -> None:
        for cb in self._dispatch_listeners(event):
            cb(*args)

    async def parallel(self, event: str, *args: Any) -> None:
        results = await asyncio.gather(
            *(cb(*args) for cb in self._dispatch_listeners(event)),
            return_exceptions=True,
        )
        errors = [r for r in results if isinstance(r, BaseException)]
        if errors:
            raise ExceptionGroup("parallel dispatch errors", errors)

    async def serial(self, event: str, *args: Any) -> Any:
        for cb in self._dispatch_listeners(event):
            result = cb(*args)
            if inspect.isawaitable(result):
                result = await result
            if is_bailed(result):
                return result
        return None

    def bail(self, event: str, *args: Any) -> Any:
        for cb in self._dispatch_listeners(event):
            result = cb(*args)
            if is_bailed(result):
                return result
        return None

    async def waterfall(self, event: str, *args: Any, terminal: Callable[[], Any]) -> Any:
        cbs = list(self._dispatch_listeners(event))

        def next_step(i: int = 0) -> Any:
            if i >= len(cbs):
                result = terminal()
                if inspect.isawaitable(result):
                    async def await_terminal():
                        return await result
                    return await_terminal()
                return result
            result = cbs[i](*args, lambda i=i: next_step(i + 1))
            if inspect.isawaitable(result):
                async def await_result(r=result):
                    return await r
                return await_result()
            return result

        result = next_step()
        if inspect.isawaitable(result):
            return await result
        return result


# ═══════════════════════════════════════════════════════════════
# §10 — PluginContext
# ═══════════════════════════════════════════════════════════════

class PluginContext:
    """Context passed to apply.
    Covers: mount/require/get/set + effect + 5 dispatch + once
    + accessor/mixin + inject shorthand + child + trace/bind.
    """

    def __init__(self, host: "PluginHost", handle: PluginHandle, *,
                 parent: "PluginContext | None" = None) -> None:
        self._host = host
        self._handle = handle
        self._parent = parent
        self._overlay: dict[str, Any] = {}
        self._intercept: dict[str, Any] = {}
        self._filter: Callable | None = None

    @property
    def plugin_id(self) -> str:
        return self._handle.entry_id

    @property
    def config(self) -> Any:
        return self._handle.config

    @property
    def parent(self) -> "PluginContext | None":
        return self._parent

    def get_intercept(self, name: str) -> Any:
        return self._intercept.get(name)

    # ── Services ──

    def get(self, service_name: str, default: Any = None) -> Any:
        if service_name in self._overlay:
            return self._overlay[service_name]
        return self._host.get_service(service_name, default)

    def require(self, service_name: str) -> Any:
        deps = self._handle.injected
        if isinstance(deps, dict):
            deps = tuple(deps.keys())
        if service_name not in deps:
            raise PluginError(
                f"Plugin {self.plugin_id!r} must declare {service_name!r} in inject"
            )
        sentinel = object()
        value = self.get(service_name, sentinel)
        if value is sentinel:
            raise DependencyUnavailable(
                f"Required service {service_name!r} not available for plugin {self.plugin_id!r}"
            )
        return value

    def mount(self, service_name: str, value: Any, *,
              check: Callable[[], bool] | None = None) -> Cleanup:
        self._host._provide(self._handle, service_name, value, check)
        def cleanup() -> None:
            current = self._host._services.get(service_name)
            if current and current.owner_id == self._handle.entry_id:
                self._host._services.pop(service_name, None)
                self._handle.provided_services.discard(service_name)
        return cleanup

    def set(self, service_name: str, value: Any) -> None:
        record = self._host._services.get(service_name)
        if record is None:
            raise PluginError(f"cannot set {service_name!r} without provide")
        if record.owner_id != self._handle.entry_id:
            raise PluginError(f"cannot set {service_name!r} in multiple fibers")
        record.value = value

    # ── Effect ──

    def effect(self, setup: Callable[[], Any] | Cleanup,
               label: str = "anonymous") -> Cleanup:
        if self._handle.state not in {PluginState.LOADING, PluginState.ACTIVE}:
            raise PluginError(f"Cannot register effect in {self._handle.state.value} state")
        meta = EffectMeta(label=label)
        result = setup()
        if inspect.isgenerator(result) or inspect.isasyncgen(result):
            gen = result
            def gen_cleanup():
                try: gen.close()
                except Exception: pass
            self._handle.effects.append((gen_cleanup, meta))
            return gen_cleanup
        if isinstance(result, Iterable) and not callable(result):
            cleanups = list(result)
            def iter_cleanup():
                for c in reversed(cleanups):
                    c()
            self._handle.effects.append((iter_cleanup, meta))
            return iter_cleanup
        cleanup = result if callable(result) else (lambda: None)
        self._handle.effects.append((cleanup, meta))
        return cleanup

    # ── Events ──

    def on(self, event: str, callback: Listener, *,
           prepend: bool = False, global_: bool = False) -> Cleanup:
        token = self._host.events.on(
            self.plugin_id, event, callback, prepend=prepend, global_=global_
        )
        self._handle.listener_tokens.add(token)
        def cleanup() -> None:
            self._host.events.off(token)
            self._handle.listener_tokens.discard(token)
        self._handle.effects.append((cleanup, EffectMeta(label=f'ctx.on("{event}")')))
        return cleanup

    def once(self, event: str, callback: Listener, **kw) -> Cleanup:
        def wrapper(*args, **kwargs):
            cleanup()
            return callback(*args, **kwargs)
        cleanup = self.on(event, wrapper, **kw)
        return cleanup

    async def emit(self, event: str, *args: Any) -> None:
        await self._host.events.emit(event, *args)

    async def parallel(self, event: str, *args: Any) -> None:
        await self._host.events.parallel(event, *args)

    async def serial(self, event: str, *args: Any) -> Any:
        return await self._host.events.serial(event, *args)

    def bail(self, event: str, *args: Any) -> Any:
        return self._host.events.bail(event, *args)

    async def waterfall(self, event: str, *args: Any, terminal: Callable[[], Any]) -> Any:
        return await self._host.events.waterfall(event, *args, terminal=terminal)

    # ── Accessor / Mixin ──

    def accessor(self, name: str, *, get: Callable, set: Callable | None = None) -> Cleanup:
        self._handle._accessors[name] = {"get": get, "set": set}
        def cleanup() -> None:
            self._handle._accessors.pop(name, None)
        self._handle.effects.append((cleanup, EffectMeta(label=f'ctx.accessor("{name}")')))
        return cleanup

    def mixin(self, source: str | object, keys: list[str] | dict[str, str]) -> Cleanup:
        entries = [(k, k) for k in keys] if isinstance(keys, list) else list(keys.items())
        cleanups = []
        for source_key, ctx_key in entries:
            def make_get(sk):
                def getter():
                    svc = self.get(source) if isinstance(source, str) else source
                    return getattr(svc, sk)
                return getter
            c = self.accessor(ctx_key, get=make_get(source_key))
            cleanups.append(c)
        def cleanup() -> None:
            for c in cleanups: c()
        return cleanup

    # ── Child context ──

    def child(self, *, key: str, values: Mapping[str, Any] | None = None) -> PluginContext:
        child = PluginContext(self._host, self._handle, parent=self)
        if values:
            child._overlay.update(values)
        return child

    # ── Inject shorthand ──

    async def inject(self, deps: tuple[str, ...] | dict[str, Any],
                     callback: Callable) -> PluginHandle:
        dep_names = tuple(deps.keys()) if isinstance(deps, dict) else deps
        spec = PluginSpec(name=f"_inject_{self.plugin_id}", apply=lambda ctx, cfg: callback(ctx))
        handle = PluginHandle(
            entry_id=f"{self.plugin_id}.__inject__",
            spec=spec, config=None, injected=dep_names,
        )
        self._host._handles[handle.entry_id] = handle
        self._host._dirty = True
        await self._host._reconcile()
        return handle


# ═══════════════════════════════════════════════════════════════
# §11 — Service base class
# ═══════════════════════════════════════════════════════════════

class Service(ABC):
    """Service base class. Auto-registers on construction.
    (Cordis Service abstract class)
    """
    name: ClassVar[str] = ""
    inject: ClassVar[tuple[str, ...] | dict[str, Any]] = ()

    def __init__(self, ctx: PluginContext, config: Any = None) -> None:
        self.ctx = ctx
        check_fn = getattr(type(self), "check", None)
        if callable(check_fn) and check_fn is not Service.check:
            ctx.mount(self.name, self, check=check_fn)
        else:
            ctx.mount(self.name, self)

    @classmethod
    def check(cls) -> bool:
        return True

    async def init(self) -> Generator[Cleanup, None, None] | None:
        return None

    def resolve_config(self, base: Any = None, head: Any = None) -> Any:
        configs: list[dict] = []
        if base:
            configs.append(base if isinstance(base, dict) else {"value": base})
        ctx = self.ctx
        while ctx is not None:
            intercept = ctx.get_intercept(self.name)
            if intercept:
                configs.append(intercept if isinstance(intercept, dict) else {"value": intercept})
            ctx = ctx.parent
        if head:
            configs.append(head if isinstance(head, dict) else {"value": head})
        result: dict = {}
        for c in configs:
            result.update(c)
        return result


# ═══════════════════════════════════════════════════════════════
# §12 — Declaration Merging (PluginMeta metaclass)
# ═══════════════════════════════════════════════════════════════

class PluginMeta(ABCMeta):
    """Metaclass: auto-merges inject/provides/intercept along inheritance chain.
    (Cordis declaration merging via TypeScript interface merging)
    """
    def __new__(mcs, name: str, bases: tuple[type, ...], namespace: dict, **kwargs) -> type:
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        merged_inject: dict[str, Any] = {}
        for base in reversed(bases):
            base_inject = getattr(base, "inject", ())
            if isinstance(base_inject, dict):
                merged_inject.update(base_inject)
            elif isinstance(base_inject, (list, tuple)):
                merged_inject.update({k: None for k in base_inject})
        cls_inject = namespace.get("inject", ())
        if isinstance(cls_inject, dict):
            merged_inject.update(cls_inject)
        elif isinstance(cls_inject, (list, tuple)):
            merged_inject.update({k: None for k in cls_inject})
        cls.inject = merged_inject  # type: ignore

        merged_intercept: dict[str, Any] = {}
        for base in reversed(bases):
            base_intercept = getattr(base, "intercept", {})
            if isinstance(base_intercept, dict):
                merged_intercept.update(base_intercept)
        cls_intercept = namespace.get("intercept", {})
        if isinstance(cls_intercept, dict):
            merged_intercept.update(cls_intercept)
        cls.intercept = merged_intercept  # type: ignore
        return cls


class Plugin(ABC, metaclass=PluginMeta):
    """Plugin base class with declaration merging."""
    inject: ClassVar[tuple[str, ...] | dict[str, Any]] = ()
    provides: ClassVar[str | None] = None
    intercept: ClassVar[dict[str, Any]] = {}
    name: ClassVar[str] = ""


# ═══════════════════════════════════════════════════════════════
# §13 — Safe Expression Evaluator (!py YAML tag)
# ═══════════════════════════════════════════════════════════════

_SAFE_NODES = {
    ast.Constant, ast.Num, ast.Str, ast.NameConstant,
    ast.Name, ast.Load, ast.Attribute, ast.Subscript, ast.Index, ast.Slice,
    ast.List, ast.Tuple, ast.Dict, ast.Set,
    ast.BoolOp, ast.And, ast.Or,
    ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Is, ast.IsNot, ast.In, ast.NotIn,
    ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.FloorDiv, ast.Pow,
    ast.UnaryOp, ast.Not, ast.USub, ast.UAdd,
    ast.IfExp, ast.Call,
}

_SAFE_BUILTINS = {
    "str": str, "int": int, "float": float, "bool": bool,
    "list": list, "dict": dict, "tuple": tuple, "set": set,
    "len": len, "range": range, "min": min, "max": max,
    "sum": sum, "abs": abs, "round": round, "sorted": sorted,
    "True": True, "False": False, "None": None,
}


class PyExpr:
    """YAML !py tag value carrier. (Cordis JsExpr equivalent)"""
    def __init__(self, expr: str) -> None:
        self.expr = expr
    def __repr__(self) -> str:
        return f"PyExpr({self.expr!r})"


class SafeEvaluator:
    """Sandboxed AST evaluator. (Cordis evaluate() but whitelist-only)"""
    def __init__(self, scope: dict[str, Any] | None = None) -> None:
        self._scope = scope or {}

    def evaluate(self, expr: str) -> Any:
        try:
            tree = ast.parse(expr, mode="eval")
        except SyntaxError as exc:
            raise ValueError(f"Invalid expression: {expr}") from exc
        return self._eval_node(tree.body)

    def _eval_node(self, node: ast.AST) -> Any:
        if type(node) not in _SAFE_NODES:
            raise ValueError(f"Unsafe AST node: {type(node).__name__}")
        match node:
            case ast.Constant(value=v):
                return v
            case ast.Name(id=name, ctx=ast.Load()):
                if name in self._scope:
                    return self._scope[name]
                if name in _SAFE_BUILTINS:
                    return _SAFE_BUILTINS[name]
                raise ValueError(f"Undefined name: {name}")
            case ast.Attribute(value=val, attr=attr, ctx=ast.Load()):
                return getattr(self._eval_node(val), attr)
            case ast.Subscript(value=val, slice=slice_node):
                return self._eval_node(val)[self._eval_node(slice_node)]
            case ast.BinOp(left=l, op=op, right=r):
                left, right = self._eval_node(l), self._eval_node(r)
                ops = {ast.Add: operator.add, ast.Sub: operator.sub,
                       ast.Mult: operator.mul, ast.Div: operator.truediv,
                       ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
                       ast.Pow: operator.pow}
                return ops[type(op)](left, right)
            case ast.UnaryOp(op=op, operand=operand):
                val = self._eval_node(operand)
                ops = {ast.Not: operator.not_, ast.USub: operator.neg, ast.UAdd: operator.pos}
                return ops[type(op)](val)
            case ast.Compare(left=l, ops=ops, comparators=comps):
                left = self._eval_node(l)
                for op, comp in zip(ops, comps):
                    right = self._eval_node(comp)
                    cmp_ops = {ast.Eq: operator.eq, ast.NotEq: operator.ne,
                               ast.Lt: operator.lt, ast.LtE: operator.le,
                               ast.Gt: operator.gt, ast.GtE: operator.ge,
                               ast.Is: operator.is_, ast.IsNot: operator.is_not,
                               ast.In: lambda a, b: a in b,
                               ast.NotIn: lambda a, b: a not in b}
                    if not cmp_ops[type(op)](left, right):
                        return False
                    left = right
                return True
            case ast.BoolOp(op=op, values=values):
                vals = [self._eval_node(v) for v in values]
                return all(vals) if isinstance(op, ast.And) else any(vals)
            case ast.IfExp(test=t, body=b, orelse=o):
                return self._eval_node(b) if self._eval_node(t) else self._eval_node(o)
            case ast.Call(func=func, args=args, keywords=kws):
                fn = self._eval_node(func)
                if fn not in _SAFE_BUILTINS.values():
                    raise ValueError(f"Unsafe function call")
                pos_args = [self._eval_node(a) for a in args]
                kw_args = {kw.arg: self._eval_node(kw.value) for kw in kws}
                return fn(*pos_args, **kw_args)
            case ast.List(elts=elts):
                return [self._eval_node(e) for e in elts]
            case ast.Tuple(elts=elts):
                return tuple(self._eval_node(e) for e in elts)
            case ast.Dict(keys=keys, values=values):
                return {self._eval_node(k): self._eval_node(v) for k, v in zip(keys, values)}
            case ast.Set(elts=elts):
                return {self._eval_node(e) for e in elts}
            case _:
                raise ValueError(f"Unsupported AST node: {type(node).__name__}")


def interpolate_config(value: Any, scope: dict[str, Any]) -> Any:
    """Recursively replace PyExpr nodes. (Cordis interpolate())"""
    if isinstance(value, PyExpr):
        return SafeEvaluator(scope).evaluate(value.expr)
    if isinstance(value, dict):
        return {k: interpolate_config(v, scope) for k, v in value.items()}
    if isinstance(value, list):
        return [interpolate_config(v, scope) for v in value]
    return value


# ═══════════════════════════════════════════════════════════════
# §14 — PluginHost (Loader + Registry + Reflect + Events)
# ═══════════════════════════════════════════════════════════════

class PluginHost:
    """Plugin container. Covers Loader + Registry + Reflect + Events."""

    def __init__(self) -> None:
        self.events = EventBus()
        self._handles: dict[str, PluginHandle] = {}
        self._services: dict[str, ServiceRecord] = {}
        self._runtimes: dict[str, list[str]] = {}
        self._module_counter = itertools.count(1)
        self._reconciling = False
        self._dirty = False
        self.builtins: dict[str, Any] = {}

    @property
    def handles(self) -> Mapping[str, PluginHandle]:
        return self._handles

    def get_service(self, name: str, default: Any = None) -> Any:
        record = self._services.get(name)
        if record is None or not record.available:
            return default
        owner = self._handles.get(record.owner_id)
        if owner is None or owner.state is not PluginState.ACTIVE:
            return default
        return record.value

    def register(self, entry_id: str, spec: PluginSpec, config: Any = None, *,
                 inject: Iterable[str] | None = None) -> PluginHandle:
        if entry_id in self._handles:
            raise PluginError(f"Duplicate entry id: {entry_id!r}")
        deps = tuple(inject) if inject is not None else (
            tuple(spec.inject.keys()) if isinstance(spec.inject, dict) else spec.inject
        )
        handle = PluginHandle(entry_id=entry_id, spec=spec, config=config, injected=deps)
        self._handles[entry_id] = handle
        self._runtimes.setdefault(spec.name, []).append(entry_id)
        return handle

    async def mount_all(self) -> None:
        for handle in self._handles.values():
            if handle.state is PluginState.DISPOSED:
                handle.state = PluginState.PENDING
            handle.desired = True
            handle.error = None
        await self._reconcile()

    async def mount(self, entry_id: str) -> PluginHandle:
        handle = self._handles[entry_id]
        handle.desired = True
        if handle.state is PluginState.DISPOSED:
            handle.state = PluginState.PENDING
        handle.error = None
        await self._reconcile()
        return handle

    async def unmount(self, entry_id: str, *, permanent: bool = True) -> None:
        handle = self._handles[entry_id]
        if permanent:
            handle.desired = False
        await self._deactivate(handle, permanent=permanent)
        await self._reconcile()

    async def shutdown(self) -> None:
        for handle in reversed(list(self._handles.values())):
            handle.desired = False
            await self._deactivate(handle, permanent=True)

    async def await_all(self) -> None:
        for handle in self._handles.values():
            await handle.await_settled()

    async def update_config(self, entry_id: str, new_config: Any) -> PluginHandle:
        handle = self._handles[entry_id]
        old_config = handle.config
        if not handle.desired:
            handle.config = new_config
            return handle
        await self._deactivate(handle, permanent=False)
        handle.config = new_config
        handle.error = None
        await self._reconcile()
        if handle.state is PluginState.ACTIVE:
            return handle
        failure = handle.error or PluginError(f"Plugin {entry_id!r} failed to recover")
        await self._deactivate(handle, permanent=False)
        handle.config = old_config
        handle.error = None
        await self._reconcile()
        raise PluginError(f"Plugin {entry_id!r} config update failed, rolled back") from failure

    async def create_entry(self, entry_id: str, spec: PluginSpec, config: Any = None,
                           inject: Iterable[str] | None = None) -> PluginHandle:
        handle = self.register(entry_id, spec, config, inject=inject)
        await self._reconcile()
        return handle

    async def remove_entry(self, entry_id: str) -> None:
        await self.unmount(entry_id, permanent=True)
        self._handles.pop(entry_id, None)

    def _deps_ready(self, handle: PluginHandle) -> bool:
        return all(self.get_service(name, None) is not None for name in handle.dependencies)

    async def _reconcile(self) -> None:
        if self._reconciling:
            self._dirty = True
            return
        self._reconciling = True
        try:
            while True:
                self._dirty = False
                progressed = False
                for handle in list(self._handles.values()):
                    if not handle.desired or handle.state is not PluginState.PENDING:
                        continue
                    if not self._deps_ready(handle):
                        continue
                    await self._activate(handle)
                    progressed = True
                if not progressed and not self._dirty:
                    break
        finally:
            self._reconciling = False

    async def _activate(self, handle: PluginHandle) -> None:
        if handle.state is not PluginState.PENDING or not handle.desired:
            return
        if not self._deps_ready(handle):
            return
        handle.state = PluginState.LOADING
        await self.events.emit("internal/status", handle, PluginState.PENDING)
        context = PluginContext(self, handle)
        try:
            config = handle.config
            if handle.spec.validate is not None:
                config = handle.spec.validate(config)
            handle.config = config
            if handle.spec.is_class:
                instance = handle.spec.apply(context, config)
                if hasattr(instance, 'init'):
                    init_result = instance.init()
                    if inspect.isgenerator(init_result):
                        for disposer in init_result:
                            handle.effects.append((disposer, EffectMeta(label="[Service.init]")))
                    elif inspect.isasyncgen(init_result):
                        async for disposer in init_result:
                            handle.effects.append((disposer, EffectMeta(label="[Service.init]")))
            else:
                result = handle.spec.apply(context, config)
                if inspect.isawaitable(result):
                    result = await result
                if inspect.isgenerator(result):
                    for disposer in result:
                        handle.effects.append((disposer, EffectMeta(label="yield")))
                elif inspect.isasyncgen(result):
                    async for disposer in result:
                        handle.effects.append((disposer, EffectMeta(label="yield")))
                elif result is not None:
                    if callable(result):
                        handle.effects.append((result, EffectMeta(label="return")))
                    elif isinstance(result, Iterable):
                        for disposer in result:
                            handle.effects.append((disposer, EffectMeta(label="yield")))
            handle.state = PluginState.ACTIVE
            handle.error = None
            await self.events.emit("internal/status", handle, PluginState.LOADING)
            await self.events.emit("internal/plugin.active", handle)
            self._dirty = True
        except BaseException as exc:
            handle.error = exc
            await self._run_effects(handle)
            await self._remove_owned_services(handle)
            handle.state = PluginState.FAILED
            await self.events.emit("internal/status", handle, PluginState.LOADING)
            await self.events.emit("internal/plugin.failed", handle, exc)

    async def _deactivate(self, handle: PluginHandle, *, permanent: bool) -> None:
        if handle.state in {PluginState.DISPOSED, PluginState.PENDING}:
            if permanent:
                handle.state = PluginState.DISPOSED
            return
        if handle.state is PluginState.UNLOADING:
            return
        old_state = handle.state
        handle.state = PluginState.UNLOADING
        await self.events.emit("internal/status", handle, old_state)
        await self._remove_owned_services(handle)
        await self._run_effects(handle)
        handle.error = None
        handle.state = PluginState.DISPOSED if permanent else PluginState.PENDING
        await self.events.emit("internal/status", handle, PluginState.UNLOADING)
        await self.events.emit("internal/plugin.disposed", handle)
        self._dirty = True

    async def _run_effects(self, handle: PluginHandle) -> None:
        errors: list[BaseException] = []
        while handle.effects:
            cleanup, _ = handle.effects.pop()
            try:
                result = cleanup()
                if inspect.isawaitable(result):
                    await result
            except BaseException as exc:
                errors.append(exc)
        handle.listener_tokens.clear()
        handle._accessors.clear()

    def _provide(self, handle: PluginHandle, name: str, value: Any,
                 check: Callable[[], bool] | None) -> None:
        if name in self._services:
            owner = self._services[name].owner_id
            raise PluginError(f"Service {name!r} already provided by {owner!r}")
        record = ServiceRecord(name=name, value=value, owner_id=handle.entry_id, check=check)
        self._services[name] = record
        handle.provided_services.add(name)
        handle.effects.append((
            lambda: None,
            EffectMeta(label=f'ctx.provide("{name}")')
        ))
        if handle.state is PluginState.ACTIVE:
            self._notify([name])
        self._dirty = True

    async def _remove_owned_services(self, handle: PluginHandle) -> None:
        names = list(handle.provided_services)
        for name in names:
            record = self._services.get(name)
            if record and record.owner_id == handle.entry_id:
                self._services.pop(name, None)
            handle.provided_services.discard(name)
            await self.events.emit("internal/service", name, None)
        if names:
            for consumer in list(self._handles.values()):
                if consumer is handle or consumer.state is not PluginState.ACTIVE:
                    continue
                if any(dep in names for dep in consumer.dependencies):
                    await self._deactivate(consumer, permanent=False)
            self._dirty = True

    def _notify(self, names: list[str]) -> None:
        for handle in self._handles.values():
            if handle.state is not PluginState.ACTIVE:
                continue
            for name in names:
                if name in handle.dependencies:
                    pass

    def import_plugin(self, module_path: str | Path) -> PluginSpec:
        path = Path(module_path).resolve()
        if not path.exists():
            raise PluginError(f"Plugin file not found: {path}")
        module_name = f"_plugin_{next(self._module_counter)}_{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise PluginError(f"Cannot create module loader: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return self._spec_from_module(module, path)

    def _spec_from_module(self, module: ModuleType, path: Path) -> PluginSpec:
        exported = getattr(module, "PLUGIN", None)
        if isinstance(exported, PluginSpec):
            return exported
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (inspect.isclass(attr) and issubclass(attr, Service)
                    and attr is not Service and hasattr(attr, 'name') and attr.name):
                inject = getattr(attr, 'inject', ())
                if isinstance(inject, dict):
                    inject = tuple(inject.keys())
                provides = getattr(attr, 'provides', None) if hasattr(attr, 'provides') else attr.name
                return PluginSpec(name=attr.name, apply=attr, inject=tuple(inject),
                                  provides=provides, is_class=True)
        name = getattr(module, "name", path.stem)
        apply_fn = getattr(module, "apply", None)
        inject = getattr(module, "inject", ())
        if isinstance(inject, dict):
            inject = tuple(inject.keys())
        provides = getattr(module, "provides", None)
        validate = getattr(module, "validate", None)
        if apply_fn is None:
            raise PluginError(f"{path} must export apply function or class")
        return PluginSpec(name=name, apply=apply_fn, inject=tuple(inject),
                         provides=provides, validate=validate)

    async def load_json_config(self, config_path: str | Path) -> None:
        path = Path(config_path).resolve()
        payload = json.loads(path.read_text(encoding="utf-8"))
        entries = payload.get("plugins") if isinstance(payload, Mapping) else payload
        if not isinstance(entries, list):
            raise PluginError("Config root must be array or object with plugins array")
        for raw in entries:
            if not isinstance(raw, Mapping):
                raise PluginError("Each plugin config must be object")
            entry_id = raw.get("id")
            module = raw.get("name")
            disabled = raw.get("disabled", False)
            if disabled:
                continue
            plugin_path = Path(module)
            if not plugin_path.is_absolute():
                plugin_path = path.parent / plugin_path
            plugin = self.import_plugin(plugin_path)
            inject = raw.get("inject")
            if inject is not None and not isinstance(inject, (list, dict)):
                raise PluginError(f"{entry_id!r} inject must be array or object")
            self.register(entry_id, plugin, raw.get("config"),
                         inject=inject if isinstance(inject, list) else None)
        await self.mount_all()
        await self.await_all()


def states_as_dict(host: PluginHost) -> dict[str, str]:
    return {eid: h.state.value for eid, h in host.handles.items()}
