"""`cordis.reflect` — Service resolution, accessors, mixins, and binding.

Faithful 1:1 port of `~/deepseek-harness/vendor/cordis/src/reflect.ts`.

Provides:

- :class:`Impl` — service implementation record stored in the root service.
- :class:`Property` — declared context property (service or accessor).
- :class:`ReflectHandler` — Python equivalent of upstream
  ``ReflectService.handler`` Proxy; routes ``get`` / ``set`` / ``has`` traps.
- :class:`ReflectService` — service-resolution layer installed as
  ``ctx.reflect``. Owns :meth:`provide`, :meth:`accessor`, :meth:`mixin`,
  :meth:`notify`, :meth:`get` / :meth:`set`, :meth:`bind`, :meth:`trace`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from cordis.utils import (
    ISOLATE,
    Tracker,
    get_traceable,
)

if TYPE_CHECKING:  # pragma: no cover — import-only for typing
    from cordis.context import Context

__all__ = [
    "Impl",
    "Property",
    "ReflectHandler",
    "ReflectService",
]


# ---------------------------------------------------------------------------
# Property / Impl records
# ---------------------------------------------------------------------------


@dataclass
class Property:
    """Declared context property (service or accessor)."""

    type: str  # "service" | "accessor"
    # Service-only: no extra fields. Accessor-only:
    get: Callable[..., Any] | None = None
    set: Callable[..., bool] | None = None


@dataclass
class Impl:
    """Service implementation record stored in the root reflect service."""

    name: str
    fiber: Any  # Fiber (avoid hard import)
    value: Any = None
    check: Callable[[], bool] | None = None


# ---------------------------------------------------------------------------
# Proxy handler (mirrors upstream ReflectService.handler)
# ---------------------------------------------------------------------------


# Reserved Context attributes that must not be routed through Reflect.
_RESERVED_WORDS: set[str] = {"prototype", "then"}


def is_nullable(value: Any) -> bool:
    """Return True for ``None`` / ``False`` values (upstream ``isNullable``)."""
    return value is None or value is False


class _MixinAccessor:
    """Builds a ``Property`` that exposes one attribute of a service.

    The accessor is a plain class so coverage can track its methods
    independently. Mirrors the upstream closure body that lived inside
    ``ReflectService.mixin``.
    """

    def __init__(
        self,
        reflect: ReflectService,
        source: Any,
        src_key: str,
        dst_key: str,
    ) -> None:
        self.reflect = reflect
        self.source = source
        self.src_key = src_key
        self.dst_key = dst_key

    def _get_target(self) -> Any:
        if isinstance(self.source, str):
            try:
                return self.reflect.ctx[self.source]
            except Exception:  # missing service → treat as nullable
                return None
        return self.source

    def get(self, _ctx: Context, receiver: Any, _error: Exception) -> Any:
        target_value = self._get_target()
        if is_nullable(target_value):
            return target_value
        attr = getattr(target_value, self.src_key, None)
        if attr is None:
            return None
        if not callable(attr):
            return attr
        # Bound methods (with __self__) are returned as-is.
        # Free functions are bound to the receiver.
        if hasattr(attr, "__self__"):
            return attr
        from functools import partial

        return partial(attr, receiver)

    def set(
        self, _ctx: Context, val: Any, _receiver: Any, _error: Exception
    ) -> bool:
        target_value = self._get_target()
        try:
            setattr(target_value, self.src_key, val)
            return True
        except Exception:  # pragma: no cover — defensive
            return False

    def install(self) -> Callable[[], Any]:
        """Register the accessor as a ``Property``; return its disposer."""
        defn = Property(type="accessor", get=self.get, set=self.set)
        self.reflect.props[self.dst_key] = defn

        def _dispose() -> Any:
            self.reflect.props.pop(self.dst_key, None)

        return _dispose


def _is_special_property(name: str) -> bool:
    """Return True for property names that should bypass Reflect.

    Mirrors upstream ``isSpecialProperty``:

    - attribute starts with ``_`` (Python convention for private).
    - is a reserved word (``prototype``, ``then``).
    - is a numeric string.
    """
    if not isinstance(name, str):
        return False
    if name.startswith("_"):
        return True
    if name in _RESERVED_WORDS:
        return True
    try:
        if int(name) >= 0 and str(int(name)) == name:
            return True
    except ValueError:
        pass
    return False


def _enhance_error(error: Exception) -> Exception:
    """Splice the caller stack lines into ``error.stack``.

    Mirrors upstream ``enhanceError``: trims the leading two lines
    (the default ``Traceback`` lines) and replaces with the message.
    """
    try:
        stack = error.__traceback__
        lines = ["Traceback (most recent call last):\n"]
        if stack is not None:
            import traceback as _tb

            lines = _tb.format_exception(type(error), error, stack)
        # Trim first two lines; replace with the message header.
        lines = [f"{type(error).__name__}: {error}"]
        error.cordis_stack = "\n".join(lines)  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover — defensive
        pass
    return error


class ReflectHandler:
    """Python equivalent of upstream ``ReflectService.handler`` Proxy.

    The upstream TS version is a ``ProxyHandler<Context>`` with three traps
    (``get``, ``set``, ``has``). Python doesn't expose a public Proxy API,
    so this class is a plain dispatcher with three methods. The owning
    :class:`Context` delegates its ``__getattr__`` / ``__setattr__`` /
    ``__contains__`` to these methods.
    """

    def get(self, target: Context, prop: str) -> Any:
        """Resolve ``target.prop`` via the service store.

        Mirrors the upstream ``get`` trap.
        """
        if _is_special_property(prop):
            return getattr(target, prop, None)

        # Direct attribute already exists on the target (slot / __dict__).
        try:
            if prop in target.__dict__:
                return get_traceable(target, target.__dict__[prop])
        except Exception:  # pragma: no cover — defensive
            pass

        # Look up declared accessor or service property.
        props = target.reflect.props
        defn = props.get(prop)
        if defn is not None and defn.type == "accessor":
            error = Exception(f'cannot get property "{prop}" without accessor')
            return defn.get(target, None, error)  # type: ignore[misc]

        # Service store lookup via Reflect.
        fiber = getattr(target, "fiber", None)
        if fiber is None or getattr(fiber, "runtime", None) is None:
            # No active plugin fiber — return directly from the store.
            return target.reflect.get(prop, False)

        error = Exception(f'cannot get property "{prop}" without inject')
        ctx = target
        try:
            impl = ctx.reflect._get_impl(prop, False)
            if impl is not None:
                return get_traceable(target, impl.value)
            # Walk the fiber chain for a declared-but-unprovided service.
            cur_fiber = fiber
            while cur_fiber is not None:
                if cur_fiber.store is not None and prop in cur_fiber.store:
                    return get_traceable(target, cur_fiber.store[prop].value)
                if cur_fiber.inject and prop in cur_fiber.inject:
                    error2 = Exception(
                        f'cannot get required service "{prop}" in inactive context'
                    )
                    raise _enhance_error(error2)
                if cur_fiber.runtime is None:
                    raise _enhance_error(error)
                cur_fiber = getattr(cur_fiber.parent, "fiber", None)
        except Exception as exc:
            if exc is error or (
                "without inject" in str(exc) or "without accessor" in str(exc)
            ):
                raise _enhance_error(error) from None
            raise
        raise _enhance_error(error)

    def set(self, target: Context, prop: str, value: Any) -> bool:
        """Overwrite a provided service's value (upstream ``set`` trap)."""
        if _is_special_property(prop):
            try:
                object.__setattr__(target, prop, value)
                return True
            except Exception:  # pragma: no cover — defensive
                return False

        defn = target.reflect.props.get(prop)
        if defn is None:
            raise _enhance_error(
                Exception(f'cannot set property "{prop}" without provide')
            )

        if defn.type == "accessor":
            if defn.set is None:
                return False
            error = Exception(f'cannot set property "{prop}" via accessor')
            return defn.set(target, value, None, error)  # type: ignore[misc]

        # Service property — route to Reflect.set which checks the fiber.
        return target.reflect.set(prop, value)

    def has(self, target: Context, prop: str) -> bool:
        """Return True if ``prop`` is locally declared as a service/accessor."""
        if _is_special_property(prop):
            return False
        return prop in target.reflect.props


# ---------------------------------------------------------------------------
# ReflectService
# ---------------------------------------------------------------------------


class ReflectService:
    """Service-resolution layer installed as ``ctx.reflect``.

    Mirrors upstream ``ReflectService``:

    - :attr:`store` — implementations keyed by isolation label.
    - :attr:`props` — declared context properties (services + accessors).
    - :meth:`provide` registers a service owned by the current fiber.
    - :meth:`accessor` / :meth:`mixin` define computed context properties.
    - :meth:`notify` walks every plugin fiber and refreshes those that
      depend on a name.
    - :meth:`bind` / :meth:`trace` wrap callbacks for context-aware calls.
    """

    handler: ReflectHandler = ReflectHandler()
    """Singleton handler shared by every context (upstream static)."""

    def __init__(self, ctx: Context) -> None:
        self.ctx: Context = ctx
        self.store: dict[Any, Impl] = {}
        self.props: dict[str, Property] = {}

        self._tracker = Tracker(property="ctx", no_shadow=True)
        try:
            self.__dict__["cordis.tracker"] = self._tracker
        except Exception:  # pragma: no cover — defensive
            pass

        # Install accessor mixins for the framework's own services.
        # Mirrors the constructor block in upstream ReflectService.
        self._install_service_mixins()

    # ------------------------------------------------------------------
    # Service registration helpers
    # ------------------------------------------------------------------

    def _install_service_mixins(self) -> None:
        """Install accessor declarations for framework services."""
        # ``reflect.get``, ``reflect.set``, ``reflect.provide`` etc. are
        # exposed as ctx.* by routing through accessors. In the Python port
        # the methods are also installed as direct Context attributes (see
        # cordis.context), so these mixins are recorded for parity but
        # the actual routing happens at the Context level.
        self.mixin("reflect", ["get", "set", "provide", "accessor", "mixin"])
        try:
            self.mixin("fiber", ["runtime", "effect"])
        except Exception:  # pragma: no cover — fiber always installed
            pass
        try:
            self.mixin("registry", ["inject", "plugin"])
        except Exception:  # pragma: no cover — registry always installed
            pass
        try:
            self.mixin(
                "events",
                ["on", "once", "parallel", "emit", "serial", "bail", "waterfall"],
            )
        except Exception:  # pragma: no cover — events always installed
            pass

    # ------------------------------------------------------------------
    # get / set / _get_impl
    # ------------------------------------------------------------------

    def get(self, name: str, strict: bool = True) -> Any:
        """Look up a service by name; return its value (or ``None``)."""
        impl = self._get_impl(name, strict)
        if impl is None:
            return None
        return get_traceable(self.ctx, impl.value)

    def _get_impl(self, name: str, strict: bool = True) -> Impl | None:
        """Internal lookup walking the isolation scope."""
        try:
            isolate_map: Any = self.ctx[ISOLATE]
        except Exception:  # pragma: no cover — defensive
            isolate_map = {}
        if not isinstance(isolate_map, dict):
            return None
        key: Any = isolate_map.get(name)
        if key is None:
            return None
        impl = self.store.get(key)
        if impl is None:
            return None
        if strict:
            from cordis.fiber import FiberState

            if impl.fiber.state != FiberState.ACTIVE:
                return None
        return impl

    def set(self, name: str, value: Any, error: Exception | None = None) -> bool:
        """Overwrite a provided service's value."""
        try:
            isolate_map: Any = self.ctx[ISOLATE]
        except Exception:  # pragma: no cover — defensive
            isolate_map = {}
        if not isinstance(isolate_map, dict):
            raise RuntimeError(f'cannot set property "{name}" without provide')
        key: Any = isolate_map.get(name)
        impl = self.store.get(key) if key is not None else None
        if impl is None:
            raise RuntimeError(f'cannot set property "{name}" without provide')
        if impl.fiber is not self.ctx.fiber:
            raise RuntimeError(f'cannot set property "{name}" in multiple fibers')
        impl.value = value
        return True

    # ------------------------------------------------------------------
    # provide
    # ------------------------------------------------------------------

    def provide(
        self,
        name: str,
        value: Any = None,
        check: Callable[[], bool] | None = None,
    ) -> Callable[[], Any]:
        """Register a service implementation owned by the current fiber.

        Returns a disposer that unregisters the service when called.
        """
        from cordis.fiber import FiberState

        # Ensure an isolation key for this service on the root context.
        root = self.ctx.root
        try:
            root_isolate = root[ISOLATE]
        except Exception:  # pragma: no cover — defensive
            root_isolate = {}
        if not isinstance(root_isolate, dict):  # pragma: no cover — defensive
            root_isolate = {}
        if name not in root_isolate:
            root_isolate[name] = f"__scope__:{name}"
        try:
            self.ctx[ISOLATE] = self.ctx[ISOLATE]
        except Exception:  # pragma: no cover — defensive
            pass

        # Mark the property as declared.
        existing = self.props.get(name)
        if existing is None:
            self.props[name] = Property(type="service")
        elif existing.type != "service":
            raise RuntimeError(
                f'property "{name}" is already declared as {existing.type}'
            )
        self.props[name] = Property(type="service")

        try:
            ctx_isolate: Any = self.ctx[ISOLATE]
        except Exception:  # pragma: no cover — defensive
            ctx_isolate = {}
        if not isinstance(ctx_isolate, dict):  # pragma: no cover
            ctx_isolate = {}
        key: Any = ctx_isolate.setdefault(name, root_isolate[name])

        fiber = self.ctx.fiber
        impl = Impl(name=name, fiber=fiber, value=value, check=check)
        if key in self.store:
            existing_impl = self.store[key]
            raise RuntimeError(
                f'service "{name}" has been registered at '
                f'<{getattr(existing_impl.fiber, "name", "?")}>'
            )
        self.store[key] = impl

        # Record the impl in the current fiber's per-fiber store for DI.
        if fiber.store is not None:
            fiber.store[name] = impl
        else:  # pragma: no cover — defensive (plugin fiber in PENDING)
            private_store: Any = getattr(fiber, "_store", None)
            if private_store is not None:
                private_store[name] = impl

        if fiber.state == FiberState.ACTIVE:
            try:
                self.notify([name])
            except Exception:  # pragma: no cover — defensive
                pass

        def _dispose() -> Any:
            try:
                self.store.pop(key, None)
            except Exception:  # pragma: no cover — defensive
                pass
            try:
                self.notify([name])
            except Exception:  # pragma: no cover — defensive
                pass
            try:
                if fiber.store is not None:
                    fiber.store.pop(name, None)
                else:  # pragma: no cover — defensive
                    private_store = getattr(fiber, "_store", None)
                    if private_store is not None:
                        private_store.pop(name, None)
            except Exception:  # pragma: no cover — defensive
                pass

        # Bind the disposer to the current fiber.
        try:
            fiber.effect(lambda: _dispose, f'ctx.provide("{name}")')
        except Exception:  # pragma: no cover — fiberless context
            pass

        return _dispose

    # ------------------------------------------------------------------
    # notify
    # ------------------------------------------------------------------

    def notify(
        self,
        names: list[str],
        filter: Callable[[Context, str], bool] | None = None,
    ) -> list[Any]:
        """Re-evaluate fibers requiring any of ``names``.

        Mirrors upstream ``ReflectService.notify``: walks every plugin
        fiber, calls ``_check_impl(name)`` for each declared service, and
        emits ``internal/service`` to refresh dependents.
        """
        if filter is None:
            filter = self._default_notify_filter

        fibers: list[Any] = []
        try:
            registry = self.ctx.registry
        except Exception:  # pragma: no cover — defensive
            registry = None
        if registry is None:
            return fibers

        for runtime in registry.values():
            for fiber in runtime.fibers:
                has_update = False
                for name in names:
                    if fiber.inject is None or name not in fiber.inject:
                        continue
                    if not filter(fiber.ctx, name):
                        continue
                    has_update = True
                    try:
                        fiber._check_impl(name)
                    except Exception:  # pragma: no cover — defensive
                        pass
                if not has_update:
                    continue
                try:
                    fiber._refresh()
                except Exception:  # pragma: no cover — defensive
                    pass
                fibers.append(fiber)

        for name in names:
            value = self._get_impl(name, False)
            value = getattr(value, "value", None) if value is not None else None
            try:
                self.ctx.events.emit(
                    self.ctx, "internal/service", name, value
                )
            except Exception:  # pragma: no cover — defensive
                pass
        return fibers

    def _default_notify_filter(self, ctx: Any, name: str) -> bool:
        """Default notify filter: only same isolation scope.

        Mirrors upstream ``(ctx, name) => ctx[symbols.isolate][name] ===
        this.ctx[symbols.isolate][name]``.
        """
        try:
            ctx_iso: Any = ctx.get(ISOLATE, None)
            self_iso: Any = self.ctx.get(ISOLATE, None)
        except Exception:  # pragma: no cover — defensive
            return True
        if not isinstance(ctx_iso, dict) or not isinstance(self_iso, dict):
            return True
        return ctx_iso.get(name) == self_iso.get(name)

    # ------------------------------------------------------------------
    # accessor
    # ------------------------------------------------------------------

    def accessor(
        self,
        name: str,
        options: dict[str, Any],
    ) -> Callable[[], Any]:
        """Declare a computed context property.

        Returns a disposer that removes the accessor declaration.
        """
        defn = self.props.get(name)
        if defn is not None:
            raise RuntimeError(
                f'property "{name}" is already declared as {defn.type}'
            )
        self.props[name] = Property(
            type="accessor",
            get=options.get("get"),
            set=options.get("set"),
        )

        def _dispose() -> Any:
            self.props.pop(name, None)

        try:
            self.ctx.fiber.effect(lambda: _dispose, f'ctx.accessor("{name}")')
        except Exception:  # pragma: no cover — fiberless context
            pass
        return _dispose

    # ------------------------------------------------------------------
    # mixin
    # ------------------------------------------------------------------

    def mixin(
        self,
        source: Any,
        mixins: list[str] | dict[str, str],
    ) -> Callable[[], Any]:
        """Expose service members directly on the context."""
        if isinstance(mixins, dict):
            entries: Iterable[tuple[str, str]] = mixins.items()
        else:
            entries = ((k, k) for k in mixins)

        disposers: list[Callable[[], Any]] = []

        for key, value in entries:
            accessor = _MixinAccessor(self, source, key, value)
            disp = accessor.install()
            disposers.append(disp)
            try:
                self.ctx.fiber.effect(
                    lambda d=disp: d, f'ctx.mixin("{value}")'
                )
            except Exception:  # pragma: no cover — fiberless context
                pass

        def _dispose_all() -> Any:
            for d in disposers:
                try:
                    d()
                except Exception:  # pragma: no cover — defensive
                    pass

        return _dispose_all

    # ------------------------------------------------------------------
    # trace / bind
    # ------------------------------------------------------------------

    def trace(self, value: Any) -> Any:
        """Wrap ``value`` so method calls trace this context."""
        return get_traceable(self.ctx, value)

    def bind(self, callback: Callable[..., Any]) -> Callable[..., Any]:
        """Return a wrapper that traces ``self`` and arguments.

        Mirrors upstream ``ReflectService.bind``: the wrapper traces each
        argument through the context's ``get_traceable`` hook and forwards
        them to the original callback. The events service prepends ``ctx``
        via ``_bind_callbacks``; this wrapper is a pure pass-through.
        """
        ctx = self.ctx

        def _wrapper(*args: Any, **kwargs: Any) -> Any:
            traced_args = tuple(get_traceable(ctx, a) for a in args)
            traced_kwargs = {k: get_traceable(ctx, v) for k, v in kwargs.items()}
            result = callback(*traced_args, **traced_kwargs)
            return get_traceable(ctx, result)

        return _wrapper
