"""`cordis.context` — DI container with provide/inject/isolate/fork/scope.

The :class:`Context` is the runtime container of cordis. Subclasses and
extensions add behavior (services, events, fibers). This module defines
the *base* lifecycle operations plus the framework's standard services
(events, reflect, registry, logger) installed at construction time.

Design (1:1 from upstream ``context.ts``):

- A context is a node in a tree. Root contexts have no parent.
- ``provide(key, value, *, dispose=None)`` stores a binding locally + LIFO.
- ``inject(key)`` walks parent chain to find a binding (or uses default).
- ``isolate(label, fn)`` clones + runs ``fn`` in a child whose ``provide``
  is scoped.
- ``fork()`` mints an empty child sharing the root.
- ``scope(label)`` is an async with that introduces a labeled scope.
- ``dispose()`` LIFO-runs every registered disposer (sync or async),
  exactly once.

Tasks 1.1–1.4 implemented the base lifecycle (provide/inject/fork/isolate/
scope/dispose, hooks, the placeholder ``ready``/``dispose`` stubs).
Tasks 1.5–1.7 add ``events``/``reflect``/``registry``/``logger`` and the
root ``Fiber`` so the upstream-style ``ctx.events.on(...)`` and
``ctx.fiber.effect(...)`` flows work end-to-end.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any, Generic, TypeVar

from cordis.disposer import Disposer, run_disposer
from cordis.utils import (
    EFFECT,
    FILTER,
    INIT_HOOKS,
    INTERCEPT,
    ISOLATE,
    RECEIVER,
    SHADOW,
    Tracker,
)

_T = TypeVar("_T")

_MISSING: Any = object()
"""Sentinel for missing-key default detection."""


class Hook(Generic[_T]):
    """A registered listener record (filled in by Event service).

    Defined here so ``Context.parallel/emit/...`` declarations remain valid
    even before the Event module imports them.
    """

    __slots__ = ("ctx", "callback")

    def __init__(self, ctx: "Context", callback: Callable[..., Any]) -> None:
        self.ctx = ctx
        self.callback = callback


# Type of a callable receive. Kept here for parity with upstream `Hook`.
def hook(func: Callable[..., Any]) -> Hook[Any]:  # noqa: ARG001
    """Return a :class:`Hook` wrapping ``func`` (legacy helper)."""
    raise NotImplementedError("hook() is not used in this port; use ctx.on().")


# Stubs used by `ctx.parallel/emit/serial/bail/waterfall`. Real implementations
# are mixed in by the Event service in `cordis.events` once that module loads.
def ready(_ctx: "Context") -> Awaitable[None]:
    raise NotImplementedError


def dispose(_ctx: "Context") -> Awaitable[None]:  # noqa: ARG001
    raise NotImplementedError


# Tracks the currently-active `Context` for `scope` resolution.
_active_ctx: ContextVar["Context | None"] = ContextVar("cordis_active_ctx", default=None)


class Context:
    """Dependency injection container with isolation, fork, and scope.

    Construction installs:

    - ``this.fiber`` — root :class:`cordis.fiber.Fiber`.
    - ``this.events`` — :class:`cordis.events.EventsService`.
    - ``this.reflect`` — :class:`cordis.reflect.ReflectService`.
    - ``this.registry`` — :class:`cordis.registry.RegistryService`.
    - ``this.logger`` — :class:`cordis.logger.LoggerService`.

    Attribute reads for unknown names are routed through :class:`Reflect`
    via :meth:`__getattr__`, mirroring upstream's ``Proxy`` handler.
    """

    __slots__ = (
        "parent",
        "root",
        "own_bindings",
        "disposers",
        "state_disposed",
        "isolated",
        "_isolation_label",
        "_descendants",
        "fiber",
        "events",
        "reflect",
        "registry",
        "logger",
        "baseUrl",
        "__dict__",
    )

    effect = EFFECT  # Symbol key for effect registration
    filter = FILTER  # Symbol key for event filter
    isolate = ISOLATE  # Symbol key for isolation map
    intercept = INTERCEPT  # Symbol key for intercept map

    is_ = "cordis.is"  # Mark for the brand check.

    def __init__(
        self,
        *,
        parent: "Context | None" = None,
        root: "Context | None" = None,
        isolation_label: str | None = None,
    ) -> None:
        # Identity.
        self.parent = parent
        self.root: "Context" = root if root is not None else self
        # Bindings + disposers.
        self.own_bindings: dict[str, Any] = {}
        self.disposers: list[Disposer] = []
        self.isolated: dict[str, "Context"] = {}
        self.state_disposed: bool = False
        self._isolation_label = isolation_label
        self._descendants: list[Context] = []
        if parent is not None:
            parent._descendants.append(self)

        # Reflect's intercept / isolate maps (small private dicts).
        # Mirrors upstream ``this[symbols.isolate] = Object.create(null)``.
        self.__dict__["_isolate_map"] = {}
        self.__dict__["_intercept_map"] = {}

        # ``baseUrl`` — upstream sets this optional relative-URL base.
        self.baseUrl: str | None = None

        # Brand marker (upstream ``Context.prototype[Context.is] = true``).
        try:
            object.__setattr__(self, "cordis.is", True)
        except Exception:  # pragma: no cover — slots may prevent on first run
            pass

        # ---- Services ----
        # Order matters: Fiber first (needs Context), then Reflect (needs
        # Fiber), then Registry, Events, Logger.

        from cordis.fiber import Fiber

        # Install the root Fiber attached to this context.
        self.fiber: Fiber = Fiber(self, {}, {}, None, _capture_outer(), is_root=True)

        from cordis.reflect import ReflectService
        from cordis.registry import RegistryService
        from cordis.events import EventsService
        from cordis.logger import LoggerService

        self.reflect = ReflectService(self)
        self.registry = RegistryService(self)
        self.events = EventsService(self)
        self.logger = LoggerService(self)

    # ------------------------------------------------------------------
    # Brand check (upstream `Context.is` uses the symbol key)
    # ------------------------------------------------------------------

    @classmethod
    def is_context(cls, value: Any) -> bool:
        """True if ``value`` is a Cordis context (upstream ``Context.is``)."""
        return bool(value) and getattr(value, "cordis.is", False) is True

    # ------------------------------------------------------------------
    # Bindings
    # ------------------------------------------------------------------

    def provide(
        self,
        key: str,
        value: Any,
        *,
        dispose: Callable[[], Any] | None = None,
    ) -> None:
        """Register ``key → value`` on this context; optionally register a disposer.

        Writes go through :class:`Reflect` as well so that ``ctx[key]``
        and ``getattr(ctx, key)`` resolve consistently.
        """
        if self.state_disposed:
            raise RuntimeError("cannot provide on a disposed context")
        self.own_bindings[key] = value
        if dispose is not None:
            self.disposers.append(Disposer(dispose, label=f"provide:{key}"))
        # Mirror to Reflect's props map so service lookups see it.
        try:
            self.reflect._service_provide_simple(key, value)
        except Exception:
            pass

    def effect(
        self,
        dispose: Callable[[], Any],
        *,
        label: str = "effect",
    ) -> None:
        """Register a disposer without creating a binding."""
        if self.state_disposed:
            raise RuntimeError("cannot add effect on a disposed context")
        self.disposers.append(Disposer(dispose, label=label))

    def inject(self, key: str, *, default: Any = _MISSING) -> Any:
        """Resolve ``key``; walk the parent chain; raise ``KeyError`` if missing."""
        if not self.state_disposed:
            active = _active_ctx.get()
            if active is not None:
                if active is self:
                    val = self._walk_local(self, key)
                    if val is not _MISSING:
                        return val
                elif self._is_ancestor_of(active):
                    val = self._local_lookup(key)
                    if val is not _MISSING:
                        return val

        return self._inject_chain(key, default)

    def _local_lookup(self, key: str) -> Any:
        active = _active_ctx.get()
        if active is None:
            return _MISSING
        return self._walk_local(active, key)

    def _walk_local(self, node: "Context", key: str) -> Any:
        if key in node.own_bindings:
            return node.own_bindings[key]
        for descendant in node._descendants:
            val = self._walk_local(descendant, key)
            if val is not _MISSING:
                return val
        return _MISSING

    def _inject_chain(self, key: str, default: Any) -> Any:
        node: "Context | None" = self
        while node is not None:
            if key in node.own_bindings:
                return node.own_bindings[key]
            node = node.parent
        if default is _MISSING:
            raise KeyError(key)
        return default

    def _is_ancestor_of(self, other: "Context") -> bool:
        node: "Context | None" = other.parent
        while node is not None:
            if node is self:
                return True
            node = node.parent
        return False

    def _is_scope_descendant(self, root: "Context", target: "Context") -> bool:
        node: "Context | None" = target
        while node is not None:
            if node is root:
                return True
            node = node.parent
        return False

    # ------------------------------------------------------------------
    # Derived contexts
    # ------------------------------------------------------------------

    def fork(self) -> "Context":
        """Return a new child context."""
        return Context(parent=self, root=self.root)

    def extend(self, meta: dict[str, Any] | None = None) -> "Context":
        """Create a child context with extra metadata.

        Mirrors upstream ``Context.extend``: returns a new context whose
        attribute lookup walks self's MRO first, then ``meta``'s keys.
        """
        child = Context(parent=self, root=self.root)
        if meta:
            for key, value in meta.items():
                try:
                    object.__setattr__(child, key, value)
                except Exception:
                    try:
                        child[key] = value  # type: ignore[index]
                    except Exception:  # pragma: no cover — defensive
                        pass
        return child

    def isolate(self, label: str, callback: Callable[["Context"], Any]) -> Any:
        """Run ``callback`` in a fresh isolated child."""
        scoped = Context(parent=self, root=self.root, isolation_label=label)
        self.isolated[label] = scoped

        if inspect.iscoroutinefunction(callback):
            async def _runner() -> Any:
                token = _active_ctx.set(scoped)
                try:
                    return await callback(scoped)
                finally:
                    _active_ctx.reset(token)

            return _runner()

        token = _active_ctx.set(scoped)
        try:
            return callback(scoped)
        finally:
            _active_ctx.reset(token)

    def scope(self, label: str) -> "_ScopeCM":
        """Async context manager introducing a labeled scope."""
        return _ScopeCM(self, label)

    # ------------------------------------------------------------------
    # Service lookups
    # ------------------------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        """Route unknown attribute reads through Reflect.

        Mirrors upstream ``Proxy(get)`` for service resolution. Special
        names (``fiber``, ``events``, etc.) are direct slots; everything
        else falls through to ``reflect.get(name)``.
        """
        # Symbols keyed via object __setattr__ already so they are reachable.
        # We deliberately do not consult `__dict__` here because the parent
        # class uses slots; Python looks up slots first then calls __getattr__.
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        if name in ("_service_props", "_resolve_marker", "_ctx"):
            raise AttributeError(name)
        if name in self.__slots__:  # type: ignore[attr-defined]
            # It's a slot attribute; let Python raise.
            raise AttributeError(name)
        # Reflect lookup.
        try:
            reflect = self.__dict__["reflect"] if "reflect" in self.__dict__ else None
        except Exception:
            reflect = None
        if reflect is None:
            reflect = getattr(self, "reflect", None)
        if reflect is not None and name not in ("reflect",):
            value = reflect.get(name, False)
            if value is not None:
                return value
        raise AttributeError(name)

    def __setitem__(self, name: str, value: Any) -> None:
        """Allow ``ctx[name] = value`` style writes via Reflect."""
        if name in (ISOLATE, INTERCEPT):
            self.__dict__[f"_{name}_map"] = value
            return
        try:
            reflect = self.__dict__.get("reflect", None) or getattr(self, "reflect", None)
        except Exception:
            reflect = None
        if reflect is None:
            object.__setattr__(self, name, value)
            return
        try:
            reflect.set(name, value)
        except Exception:
            # Fall back to direct assignment.
            object.__setattr__(self, name, value)

    def __getitem__(self, name: str) -> Any:
        """Allow ``ctx[name]`` style reads (upstream ``this[symbols.isolate]``).

        Special names (isolate/intercept) return the framework's internal
        maps; everything else is routed through Reflect.
        """
        if name == ISOLATE:
            return self.__dict__.get("_isolate_map", {})
        if name == INTERCEPT:
            return self.__dict__.get("_intercept_map", {})
        reflect = self.__dict__.get("reflect", None) or getattr(self, "reflect", None)
        if reflect is None:
            raise KeyError(name)
        result = reflect.get(name, False)
        if result is None:
            raise KeyError(name)
        return result

    def __contains__(self, name: str) -> bool:
        try:
            self[name]
            return True
        except Exception:
            return False

    def get(self, name: str, default: Any = None) -> Any:  # type: ignore[override]
        """Map-like ``ctx.get(name, default)`` access."""
        try:
            return self[name]
        except Exception:
            return default

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def dispose(self) -> None:
        """Run all registered disposers in reverse-registration order; idempotent."""
        if self.state_disposed:
            return
        self.state_disposed = True
        disposers = self.disposers
        self.disposers = []
        for disp in reversed(disposers):
            try:
                await run_disposer(disp)
            except Exception as e:  # noqa: BLE001
                import logging

                logging.getLogger(__name__).warning(
                    f"disposer {disp.label!r} raised {type(e).__name__}: {e}"
                )

    def emit(self, *args: Any) -> None:
        """Mix-in: ``ctx.emit(...)`` mirrors ``ctx.events.emit(...)``.

        Upstream mixes events methods directly into the Context via the
        ``ReflectService.handler`` Proxy. For Python we expose them as
        plain sync methods here.
        """
        self.events.emit(*args)

    def parallel(self, *args: Any) -> Any:
        """Mix-in: ``ctx.parallel(name, ...)`` -> ``ctx.events.parallel(...)``."""
        return self.events.parallel(*args)

    async def serial(self, *args: Any) -> Any:
        """Mix-in: ``ctx.serial(name, ...)`` -> ``ctx.events.serial(...)``."""
        result = self.events.serial(*args)
        if inspect.isawaitable(result):
            return await result
        return result

    def bail(self, *args: Any) -> Any:
        """Mix-in: ``ctx.bail(name, ...)`` -> ``ctx.events.bail(...)``."""
        return self.events.bail(*args)

    def waterfall(self, *args: Any) -> Any:
        """Mix-in: ``ctx.waterfall(name, ...)`` -> ``ctx.events.waterfall(...)``."""
        return self.events.waterfall(*args)

    def on(  # type: ignore[no-untyped-def]
        self,
        name: str,
        listener: Callable[..., Any],
        *args: Any,
        prepend: bool | None = None,
        global_: bool | None = None,
        **kwargs: Any,
    ) -> Callable[[], bool]:
        """Mix-in: ``ctx.on(...)`` -> ``ctx.events.on(...)``.

        Accepts either positional ``options`` or keyword ``prepend`` /
        ``global_`` form for convenience.
        """
        if prepend is not None or global_ is not None:
            options = {
                "prepend": bool(prepend) if prepend is not None else False,
                "global": bool(global_) if global_ is not None else False,
            }
            return self.events.on(name, listener, options)
        if "prepend" in kwargs or "global" in kwargs:
            options = {
                "prepend": bool(kwargs.pop("prepend", False)),
                "global": bool(kwargs.pop("global", False)),
            }
            return self.events.on(name, listener, options)
        return self.events.on(name, listener, *args)

    def once(  # type: ignore[no-untyped-def]
        self,
        name: str,
        listener: Callable[..., Any],
        *args: Any,
        prepend: bool | None = None,
        global_: bool | None = None,
        **kwargs: Any,
    ) -> Callable[[], bool]:
        """Mix-in: ``ctx.once(...)`` -> ``ctx.events.once(...)``."""
        if prepend is not None or global_ is not None:
            options = {
                "prepend": bool(prepend) if prepend is not None else False,
                "global": bool(global_) if global_ is not None else False,
            }
            return self.events.once(name, listener, options)
        if "prepend" in kwargs or "global" in kwargs:
            options = {
                "prepend": bool(kwargs.pop("prepend", False)),
                "global": bool(kwargs.pop("global", False)),
            }
            return self.events.once(name, listener, options)
        return self.events.once(name, listener, *args)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _capture_outer() -> Callable[[], list[str]]:
    """Capture outer stack frames for effect diagnostics.

    Mirrors upstream ``buildOuterStack``.
    """
    from cordis.utils import build_outer_stack

    return build_outer_stack(0)


# ---------------------------------------------------------------------------
# Scope CM
# ---------------------------------------------------------------------------


class _ScopeCM:
    """Async context manager implementing ``Context.scope()``."""

    __slots__ = ("_parent", "_label", "_scoped", "_token", "_new_disposer_start")

    def __init__(self, parent: Context, label: str) -> None:
        self._parent = parent
        self._label = label
        self._scoped = parent.isolated.get(label) or Context(
            parent=parent, root=parent.root, isolation_label=label
        )
        parent.isolated.setdefault(label, self._scoped)
        self._token: Any = None
        self._new_disposer_start = 0

    @property
    def scoped(self) -> Context:
        return self._scoped

    async def __aenter__(self) -> Context:
        self._token = _active_ctx.set(self._scoped)
        self._new_disposer_start = len(self._scoped.disposers)
        return self._scoped

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        try:
            new_disposers = self._scoped.disposers[self._new_disposer_start:]
            for disp in reversed(new_disposers):
                await run_disposer(disp)
        finally:
            if self._token is not None:
                _active_ctx.reset(self._token)


__all__ = [
    "Context",
    "Hook",
    "hook",
    "ready",
    "dispose",
    "EFFECT",
    "ISOLATE",
    "INTERCEPT",
    "FILTER",
]
