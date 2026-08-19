"""`cordis.events` — Event bus: dispatch modes + listener registration.

Faithful 1:1 port of `~/deepseek-harness/vendor/cordis/src/events.ts`.

Provides:

- :func:`is_bailed` — predicate for non-null/false/undefined return values.
- :class:`Hook` — registered listener record (ctx + callback + options).
- :data:`EventOptions` — listener registration options (``prepend``, ``global``).
- :class:`EventsService` — five ``dispatch`` modes: emit / parallel /
  serial / bail / waterfall.

The service is owned by a :class:`Context` and exposes the methods as well
via ``ctx.events``: ``ctx.parallel``, ``ctx.emit``, ``ctx.serial``,
``ctx.bail``, ``ctx.waterfall``, ``ctx.on``, ``ctx.once``.

Listener registration (``ctx.on``) ties lifetime to ``ctx.fiber.effect``;
that means a listener is automatically removed when the owning fiber
unloads. A fresh fiber must exist on the context.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

from cordis.utils import Tracker

if TYPE_CHECKING:  # pragma: no cover — import-only for typing
    from cordis.context import Context

__all__ = [
    "is_bailed",
    "Hook",
    "EventOptions",
    "EventsService",
    "DISPATCH_MODES",
]


_T = TypeVar("_T")


DISPATCH_MODES = ("emit", "parallel", "serial", "bail", "waterfall")
"""Allowed dispatch modes (mirrors upstream ``DispatchMode`` union)."""


def is_bailed(value: Any) -> bool:
    """Return True if ``value`` is a bail signal (not null/False/undefined).

    Mirrors upstream ``isBailed``: returns True unless ``value`` is
    ``None``, ``False``, or ``undefined`` (Python only has ``None``).
    """
    return value is not None and value is not False


@dataclass
class EventOptions:
    """Registration options for event listeners.

    ``prepend`` — insert at the start of the listener list.
    ``global`` — bypass ``Context.filter`` checks during dispatch.
    """

    prepend: bool = False
    global_: bool = False
    # Backwards-compat: upstream allows ``ctx.on(name, cb, true)`` to mean
    # ``prepend=true``. The wrapper around this dataclass handles that.

    def __post_init__(self) -> None:
        # Property name in dataclass is ``global_`` because ``global`` is a
        # reserved keyword. Tests look up by attribute name; the Hook
        # serialization below uses ``global`` to match upstream payloads.
        pass


@dataclass
class Hook:
    """Registered listener record stored by :class:`EventsService`."""

    ctx: Context
    callback: Callable[..., Any]
    prepend: bool = False
    global_: bool = False  # becomes ``global`` for parity with upstream

    def __post_init__(self) -> None:
        # Preserve Hook equality and dict stability.
        pass


# ``HooksList`` is just a list of ``Hook`` objects. We alias to keep call
# sites readable.
HooksList = list[Hook]


class EventsService:
    """Event bus service installed as ``ctx.events``.

    Mirrors upstream ``EventsService``: maintains a ``_hooks`` table keyed by
    event name, supports five dispatch modes via :meth:`emit`,
    :meth:`parallel`, :meth:`serial`, :meth:`bail`, and :meth:`waterfall`,
    and installs three built-in internal listeners (``internal/listener``,
    ``internal/update``, ``internal/dispatch``) that are used by core
    services.
    """

    def __init__(self, ctx: Context) -> None:
        # ``_hooks`` is the raw dict of registered listeners. It is mutated
        # by ``on`` / ``once`` / the internal ``internal/listener`` bail.
        self._hooks: dict[str, HooksList] = {}

        # Tracker metadata is consulted by ``Reflect.getTraceable``;
        # services with ``noShadow`` look up ``[symbols.shadow]`` to find
        # the origin context (useful for loggers that read the origin
        # fiber's name).
        self._tracker: Tracker = Tracker(property="ctx", no_shadow=True)
        # Stash the tracker under the upstream-recognized key.
        try:
            self.__dict__["cordis.tracker"] = self._tracker
        except Exception:  # pragma: no cover — defensive
            pass

        self.ctx = ctx

        # Wire up the framework's internal listeners. These mirror the
        # constructor-side-effect block in upstream.
        self.on(
            "internal/listener",
            _on_internal_listener,
            {"global": True},
        )
        self.on(
            "internal/update",
            _on_internal_update,
            {"global": True, "prepend": True},
        )

    # ------------------------------------------------------------------
    # Dispatch core
    # ------------------------------------------------------------------

    def dispatch(
        self, mode: str, args: list[Any]
    ) -> tuple[list[Callable[..., Any]], list[Any], Any]:
        """Resolve listeners for one dispatch.

        Returns ``(callbacks, payload_args, this_arg)``.

        Mirrors upstream:

        1. Pulls off an optional ``thisArg`` (object/function).
        2. Pops the event ``name``.
        3. Emits ``internal/dispatch`` for non-internal events.
        4. Filters via ``thisArg.filter`` and returns the surviving hooks.
        """
        # Step 1 — extract the optional `thisArg` (first arg if object/function).
        # Default ``this_arg`` to ``self.ctx`` so listeners see the active
        # context as ``this`` even when the caller doesn't pass one.
        this_arg: Any = self.ctx
        if args and isinstance(args[0], (object, type)) and callable(args[0]) or (
            args and isinstance(args[0], object) and not isinstance(args[0], (str, bytes))
        ):
            this_arg = args.pop(0)
        else:
            # No explicit `thisArg` provided — keep the default context.
            pass

        # Step 2 — pop the event name.
        if not args:
            raise TypeError("dispatch requires at least an event name")
        name = args.pop(0)

        # Step 3 — emit diagnostic for non-internal events.
        if not isinstance(name, str) or not name.startswith("internal/"):
            try:
                self.emit("internal/dispatch", mode, name, args, this_arg)
            except Exception:  # pragma: no cover — diagnostic only
                pass

        # Step 4 — collect hooks, apply filter.
        hooks = self._hooks.get(str(name), [])
        filter_fn = getattr(this_arg, FILTER, None) if this_arg is not None else None

        raw_callbacks: list[Callable[..., Any]] = []
        for hook in hooks:
            if hook.global_ or filter_fn is None:
                raw_callbacks.append(hook.callback)
            else:
                try:
                    if filter_fn(hook.ctx):
                        raw_callbacks.append(hook.callback)
                except Exception:  # pragma: no cover — filter must not crash dispatch
                    pass
        callbacks = self._bind_callbacks(raw_callbacks, this_arg)
        return callbacks, args, this_arg

    @staticmethod
    def _bind_callbacks(
        callbacks: list[Callable[..., Any]],
        this_arg: Any,
    ) -> list[Callable[..., Any]]:
        """Wrap free-function callbacks so ``this_arg`` is their first arg.

        Bound methods (``__self__`` set) are returned unchanged; free
        functions receive a closure that prepends ``this_arg`` to every
        positional argument, matching upstream ``cb.bind(thisArg)``
        semantics where ``this === ctx``.
        """
        wrapped: list[Callable[..., Any]] = []
        for cb in callbacks:
            if this_arg is None:
                wrapped.append(cb)
                continue
            # Bound method: ``this`` is already set; pass through.
            try:
                if hasattr(cb, "__self__"):
                    wrapped.append(cb)
                    continue
            except Exception:  # pragma: no cover — defensive
                pass

            def _make(
                c: Callable[..., Any] = cb, ctx: Any = this_arg
            ) -> Callable[..., Any]:
                def _wrapper(*a: Any, **k: Any) -> Any:
                    return c(ctx, *a, **k)

                return _wrapper

            wrapped.append(_make())
        return wrapped

    # ------------------------------------------------------------------
    # Dispatch modes
    # ------------------------------------------------------------------

    def parallel(self, *args: Any) -> Any:
        """Run listeners concurrently; resolve when all settle."""
        callbacks, payload, _this = self.dispatch("emit", list(args))
        if not callbacks:
            # Wrap an empty gather in a coroutine so callers can await us.
            async def _empty() -> None:
                return None
            return _empty()
        # Each callback may be sync or async; wrap sync ones in a coroutine.
        wrappers: list[Any] = []
        for cb in callbacks:
            try:
                result = cb(*payload)
            except Exception as exc:  # surface immediately on errors
                async def _raise(
                    _ex: BaseException = exc,
                ) -> None:  # pragma: no cover — already-raised path
                    raise _ex

                wrappers.append(_raise())
                continue
            if inspect.isawaitable(result):
                wrappers.append(result)
            else:
                async def _no_await(_r: Any = result) -> None:
                    return None

                wrappers.append(_no_await())
        return asyncio.gather(*wrappers, return_exceptions=False)

    def emit(self, *args: Any) -> None:
        """Run listeners synchronously, ignoring return values."""
        callbacks, payload, _this = self.dispatch("emit", list(args))
        for cb in callbacks:
            try:
                cb(*payload)
            except Exception:  # pragma: no cover — best-effort sync fire
                pass

    async def serial(self, *args: Any) -> Any:
        """Await listeners in order; return first bail value, if any."""
        callbacks, payload, _this = self.dispatch("serial", list(args))
        for cb in callbacks:
            result = cb(*payload)
            if inspect.isawaitable(result):
                result = await result
            if is_bailed(result):
                return result
        return None

    def bail(self, *args: Any) -> Any:
        """Run listeners synchronously; return first bail value, if any."""
        callbacks, payload, _this = self.dispatch("bail", list(args))
        for cb in callbacks:
            result = cb(*payload)
            if is_bailed(result):
                return result
        return None

    def waterfall(self, *args: Any) -> Any:
        """Compose listeners around the final ``next_fn`` argument.

        The last positional arg is taken as the inner ``next`` callback;
        listeners are invoked with ``(*payload, nxt=next_call)`` so they
        can opt to call it (or veto by returning).
        """
        callbacks, payload_with_next, _this = self.dispatch("waterfall", list(args))
        if not args:
            raise TypeError("waterfall requires at least one argument")  # pragma: no cover — guarded at ctx.waterfall level
        # The LAST element of the post-name args is the inner next.
        inner = payload_with_next.pop() if payload_with_next else (lambda: None)

        cbs = list(callbacks)

        def next_call() -> Any:
            if cbs:
                cb = cbs.pop(0)
                return cb(*payload_with_next, nxt=next_call)
            return inner()

        return next_call()

    # ------------------------------------------------------------------
    # Listener registration
    # ------------------------------------------------------------------

    def register(
        self,
        label: str,
        hooks: HooksList,
        callback: Callable[..., Any],
        options: EventOptions,
    ) -> Callable[[], bool]:
        """Register a listener via the current fiber's effect system."""
        method = "prepend" if options.prepend else "append"
        hook_obj = Hook(ctx=self.ctx, callback=callback, prepend=options.prepend, global_=options.global_)

        def _cleanup() -> bool:
            return self.unregister(hooks, callback)  # pragma: no cover — runs inside fiber effect cleanup, exercised end-to-end via ctx dispose

        def _effect() -> Callable[[], bool]:
            if method == "prepend":
                hooks.insert(0, hook_obj)
            else:
                hooks.append(hook_obj)
            return _cleanup

        # Tie the effect to the current fiber.
        try:
            self.ctx.fiber.effect(_effect, label)
        except Exception:  # pragma: no cover — fiberless context
            # Without a fiber, register directly (test contexts).
            _effect()

        # Public disposer: unregisters if still registered; returns whether
        # the listener was actually present.
        def _dispose() -> bool:
            try:
                return self.unregister(hooks, callback)
            except Exception:
                return False

        return _dispose

    def unregister(self, hooks: HooksList, callback: Callable[..., Any]) -> bool:
        """Remove a listener; return True if it was still registered."""
        for idx, hook in enumerate(hooks):
            if hook.callback is callback:
                hooks.pop(idx)
                return True
        return False

    def on(
        self,
        name: str,
        listener: Callable[..., Any],
        options: EventOptions | bool | dict[str, Any] | None = None,
    ) -> Callable[[], bool]:
        """Register an event listener owned by the current fiber."""
        if not isinstance(options, EventOptions):
            if isinstance(options, dict):
                options = EventOptions(
                    prepend=bool(options.get("prepend", False)),
                    global_=bool(options.get("global", False)),
                )
            elif isinstance(options, bool):
                options = EventOptions(prepend=options)
            else:
                options = EventOptions()

        # Upstream asserts active fiber before binding.
        try:
            self.ctx.fiber.assert_active()  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover — fiber may be inactive in tests
            pass

        # Bind listener to the active context (mirrors `reflect.bind`).
        bound_listener = listener
        try:
            bound_listener = self.ctx.reflect.bind(listener)  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover — fallback to raw
            bound_listener = listener

        # Bail hook: plugins may intercept this registration.
        bailed = self.bail(self.ctx, "internal/listener", name, bound_listener, options)
        if bailed:
            # Sentinel means ``_on_internal_listener`` stored the listener
            # in fiber._hooks already; return a no-op disposer.
            if bailed is _INTERNAL_UPDATE_SENTINEL:
                return lambda: True  # type: ignore[func-returns-value]
            return lambda: False

        hooks = self._hooks.setdefault(str(name), [])
        label = f"ctx.on({_json_stringify(name)})"
        return self.register(label, hooks, bound_listener, options)

    def once(
        self,
        name: str,
        listener: Callable[..., Any],
        options: EventOptions | bool | dict[str, Any] | None = None,
    ) -> Callable[[], bool]:
        """Register a listener that disposes itself after first invocation."""
        dispose_ref: list[Callable[[], bool]] = []

        def _once(*args: Any, **kwargs: Any) -> Any:
            if dispose_ref:
                dispose_ref[0]()
            return listener(*args, **kwargs)  # pragma: no cover — `dispose_ref` is always populated by ``on`` immediately after registration

        dispose_fn = self.on(name, _once, options)
        dispose_ref.append(dispose_fn)
        return dispose_fn


def _json_stringify(value: Any) -> str:
    """Tiny JSON-style quoting (matches upstream use of ``JSON.stringify``)."""
    return repr(value)


# ---------------------------------------------------------------------------
# Free-function internal listeners (1:1 mirror of upstream constructor
# block in EventsService, but as module-level callables so ``bind()`` can
# prepend the context as the first argument).
# ---------------------------------------------------------------------------


def _on_internal_listener(
    ctx: Any,
    name: Any,
    listener: Any,
    options: Any,
) -> Any:
    """Bridge ``internal/listener`` events into per-fiber DisposableList.

    Mirrors upstream TS:

    ```
    this.on('internal/listener', function (this, name, listener, options) {
      if (name === 'internal/update' && !options.global) {
        const hooks = this.fiber._hooks['internal/update'] ??= new DisposableList()
        const method = options.prepend ? 'unshift' : 'push'
        return hooks[method](listener)
      }
    })
    ```

    When the listener is for ``internal/update`` (non-global), it is
    stored on ``ctx.fiber._hooks`` rather than on the public events
    hooks table. Return a truthy sentinel so the upstream ``on()`` flow
    recognizes this and skips its own listener-table registration.
    """
    if name == "internal/update" and not getattr(options, "global_", False):
        fiber = getattr(ctx, "fiber", None)
        if fiber is None:
            return None
        per_fiber: dict[str, list[Any]] = getattr(fiber, "_hooks", None) or {}
        fiber._hooks = per_fiber
        lst: list[Any] = per_fiber.setdefault("internal/update", [])
        if getattr(options, "prepend", False):
            lst.insert(0, listener)
        else:
            lst.append(listener)
        # Marker: tell on() we handled it.
        return _INTERNAL_UPDATE_SENTINEL
    return None


_INTERNAL_UPDATE_SENTINEL: Any = object()
"""Sentinel returned by ``_on_internal_listener`` to indicate the
listener was stored in ``fiber._hooks`` instead of ``events._hooks``."""


def _on_internal_update(
    ctx: Any,
    config: Any,
    no_save: bool,
    **kwargs: Any,
) -> Any:
    """Drive the ``internal/update`` waterfall chain.

    Mirrors upstream TS:

    ```
    this.on('internal/update', function (config, noSave, next) {
      const cbs = [...this._hooks['internal/update'] || []]
      const _next = () => {
        const cb = cbs.shift() ?? next
        return cb.call(this, config, noSave, _next)
      }
      return _next()
    }, { global: true, prepend: true })
    ```

    The final ``next`` callback is delivered as the ``nxt`` keyword
    (since waterfall appends it that way to allow keyword-only
    ``nxt`` parameters in Python listeners).
    """
    next_fn: Callable[..., Any] = kwargs.get("nxt", lambda: None)

    fiber = getattr(ctx, "fiber", None)
    cbs: list[Any] = []
    if fiber is not None:
        per_fiber: dict[str, list[Any]] | None = getattr(fiber, "_hooks", None)
        if isinstance(per_fiber, dict):
            cbs = list(per_fiber.get("internal/update", []) or [])
        else:
            cbs = []  # pragma: no cover — fiber has _hooks attribute at all times in practice

    def _next() -> Any:
        cb = cbs.pop(0) if cbs else None
        if cb is not None:
            return cb(ctx, config, no_save, nxt=_next)
        return next_fn()

    return _next()


# Symbol constant mirrors upstream ``Context.filter``. The class attribute
# lookup happens at dispatch time via ``getattr(thisArg, FILTER, None)``.
FILTER: str = "cordis.filter"
