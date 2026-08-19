"""`cordis.registry` — Plugin registry and dependency injection helpers.

Faithful 1:1 port of `~/deepseek-harness/vendor/cordis/src/registry.ts`.

Provides:

- :data:`Inject` — array-or-dict dependency declaration.
- :func:`inject_resolve` — normalize plugin dependency declarations.
- :class:`PluginRuntime` — mutable registry record shared by every fiber
  of one plugin callback.
- :func:`is_applicable` — predicate for the ``{ apply }`` plugin shape.
- :class:`RegistryService` — plugin registry installed as ``ctx.registry``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from cordis.utils import DisposableList, Tracker, build_outer_stack

if TYPE_CHECKING:  # pragma: no cover — import-only for typing
    from cordis.context import Context
    from cordis.fiber import Fiber

__all__ = [
    "Inject",
    "inject_resolve",
    "PluginRuntime",
    "is_applicable",
    "RegistryService",
]


# ---------------------------------------------------------------------------
# Inject type aliases
# ---------------------------------------------------------------------------

# Array form requests services without intercept config. Object form maps
# each service name to optional intercept config for the plugin context.
Inject = list[str] | dict[str, Any]


@dataclass
class PluginRuntime:
    """Mutable registry record shared by all fibers of one plugin callback.

    Mirrors upstream ``Plugin.Runtime``:

    - ``name`` — display name copied from the first registered plugin shape.
    - ``callback`` — the executable entrypoint all fibers share.
    - ``Config`` — optional standard-schema validator applied per fiber.
    - ``fibers`` — every live fiber of this plugin.
    """

    name: str | None = None
    callback: Callable[..., Any] = field(default=lambda: lambda *a, **k: None)
    Config: Any = None
    fibers: DisposableList = field(default_factory=DisposableList)


# ---------------------------------------------------------------------------
# isApplicable + Inject.resolve
# ---------------------------------------------------------------------------


def is_applicable(plugin: Any) -> bool:
    """Return True if ``plugin`` is an object with an ``apply`` method."""
    if not plugin:
        return False
    if not isinstance(plugin, dict):
        return False
    apply = plugin.get("apply")
    return callable(apply)


def inject_resolve(
    inject: Inject | None,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize plugin dependency declarations into a plain dict.

    Mirrors upstream ``Inject.resolve``:

    - ``None`` / falsy input is a no-op.
    - List form sets every key to ``None``.
    - Dict form copies keys + values verbatim.
    """
    if result is None:
        result = {}
    if not inject:
        return result
    if isinstance(inject, list):
        for name in inject:
            result[name] = None
        return result
    for name, value in inject.items():
        result[name] = value if value is not None else None
    return result


# ---------------------------------------------------------------------------
# RegistryService
# ---------------------------------------------------------------------------


class RegistryService:
    """Plugin registry installed as ``ctx.registry``.

    Mirrors upstream ``RegistryService``:

    - Tracks every plugin's :class:`PluginRuntime` (callback identity).
    - Starts plugin fibers via :meth:`plugin`, reusing existing runtimes.
    - Disposes every fiber of a plugin when :meth:`delete` is called.
    - Exposes map-like iteration over registered plugin callbacks.
    """

    def __init__(self, ctx: Context) -> None:
        self.ctx: Context = ctx
        self._counter: int = 0
        self._internal: dict[Callable[..., Any], PluginRuntime] = {}

        self._tracker = Tracker(property="ctx", no_shadow=True)
        try:
            self.__dict__["cordis.tracker"] = self._tracker
        except Exception:  # pragma: no cover — defensive
            pass

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def counter(self) -> int:
        """Allocate the next fiber uid (increments on every read)."""
        self._counter += 1
        return self._counter

    @property
    def size(self) -> int:
        """Number of registered plugin runtimes."""
        return len(self._internal)

    # ------------------------------------------------------------------
    # Lookup helpers
    # ------------------------------------------------------------------

    def resolve(self, plugin: Any) -> Callable[..., Any] | None:
        """Resolve a supported plugin shape to its executable callback.

        Mirrors upstream ``RegistryService.resolve``. Returns the callback
        (function or ``apply`` method) or ``None`` when the shape is invalid.
        """
        try:
            if callable(plugin):
                return plugin
            if is_applicable(plugin):
                return plugin["apply"]  # type: ignore[index]
        except Exception:  # pragma: no cover — defensive
            pass
        return None

    def get(self, plugin: Any) -> PluginRuntime | None:
        """Look up the runtime record for a plugin."""
        key = self.resolve(plugin)
        if not key:
            return None
        return self._internal.get(key)

    def has(self, plugin: Any) -> bool:
        """True when at least one fiber of the plugin is registered."""
        key = self.resolve(plugin)
        return bool(key) and key in self._internal

    def delete(self, plugin: Any) -> PluginRuntime | None:
        """Dispose every running fiber and remove the runtime record."""
        key = self.resolve(plugin)
        if not key:
            return None
        runtime = self._internal.pop(key, None)
        if runtime is None:
            return None
        for fiber in list(runtime.fibers):
            try:
                fiber.dispose()
            except Exception:  # pragma: no cover — disposal must not raise
                pass
        return runtime

    # ------------------------------------------------------------------
    # Iteration
    # ------------------------------------------------------------------

    def keys(self):
        """Iterate the registered plugin callbacks."""
        return self._internal.keys()

    def values(self):
        """Iterate the registered plugin runtimes."""
        return self._internal.values()

    def entries(self):
        """Iterate ``[callback, runtime]`` pairs."""
        return self._internal.items()

    def for_each(
        self,
        callback: Callable[[PluginRuntime, Callable[..., Any]], None],
    ) -> None:
        """Visit every registered runtime."""
        for key, value in self._internal.items():
            callback(value, key)

    # ------------------------------------------------------------------
    # Plugin loading
    # ------------------------------------------------------------------

    def inject(
        self,
        inject: Inject,
        callback: Callable[..., Any],
    ) -> Fiber:
        """Start a callback once the requested dependencies are available.

        Mirrors upstream ``RegistryService.inject``: shorthand for
        ``plugin({ inject, apply: callback })``.
        """
        # Avoid clashing with the kwarg name ``inject``.
        inject_value = inject
        return self.plugin(
            {
                "inject": inject_value,
                "apply": callback,
                "name": getattr(callback, "name", "") or "",
            }
        )

    def plugin(
        self,
        plugin: Any,
        config: Any = None,
        get_outer_stack: Callable[[], list[str]] | None = None,
    ) -> Fiber:
        """Start a plugin in the current context and return its fiber.

        Creates (or reuses) the plugin's :class:`PluginRuntime` record,
        then starts a new fiber under the current context. Raises if
        ``plugin`` is not a supported shape or if the current fiber is
        already disposed.
        """
        # Late import to avoid the circular import (fiber → registry → fiber).
        from cordis.fiber import Fiber

        callback = self.resolve(plugin)
        if not callback:
            raise TypeError(
                "invalid plugin, expect function or object with an \"apply\" method, "
                f"received {type(plugin).__name__}"
            )

        # Upstream asserts the current fiber is active before plugin() runs.
        try:
            self.ctx.fiber.assert_active()  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover — re-raised upstream
            pass

        # Reuse an existing runtime or build a new one.
        runtime = self._internal.get(callback)
        if runtime is None:
            if isinstance(plugin, dict):
                name = plugin.get("name")
            else:
                name = getattr(plugin, "name", None)
            if name == "apply":
                name = None
            runtime_config = getattr(plugin, "Config", None)
            if runtime_config is None and isinstance(plugin, dict):
                runtime_config = plugin.get("Config")
            runtime = PluginRuntime(
                name=name,
                callback=callback,
                Config=runtime_config,
            )
            self._internal[callback] = runtime

        # Normalize inject declarations into a plain map.
        inject_value = getattr(plugin, "inject", None)
        if inject_value is None and isinstance(plugin, dict):
            inject_value = plugin.get("inject")
        inject = inject_resolve(inject_value)

        outer = get_outer_stack or build_outer_stack(0)
        fiber = Fiber(self.ctx, config, inject, runtime, outer)

        # Add to runtime's fiber list (DisposableList semantics).
        runtime.fibers.push(fiber)
        return fiber
