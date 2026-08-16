"""PluginContext — the only API surface plugins see during ``apply``.

Responsibilities (ONLY these):
- Service lookup: ``get`` / ``require`` / ``set`` (delegates to host)
- Service mount: ``mount`` (delegates to host, registers cleanup)
- Effect registration: ``effect`` (appends to handle)
- Event proxy: ``on`` / ``once`` / ``emit`` / ``parallel`` / ``serial`` / ``bail`` / ``waterfall``
- Accessor/mixin: computed properties on ctx
- Child context: run-scoped overlay

PluginContext does NOT own any data. It delegates to:
- ``PluginHost`` for service table + event bus
- ``PluginHandle`` for effect accumulation

This ensures plugins cannot bypass the host or manipulate handles directly.
"""

from __future__ import annotations

import contextlib
import inspect
from collections.abc import Callable, Iterable, Mapping
from typing import TYPE_CHECKING, Any

from lca.layer0_infra.plugin.kernel._effect_meta import EffectMeta
from lca.layer0_infra.plugin.kernel._types import (
    Cleanup,
    DependencyUnavailable,
    Listener,
    PluginError,
    PluginState,
)

if TYPE_CHECKING:
    from lca.layer0_infra.plugin.kernel._handle import PluginHandle
    from lca.layer0_infra.plugin.kernel._host import PluginHost


class PluginContext:
    """Plugin-facing API. All operations proxy to host + handle."""

    def __init__(
        self,
        host: PluginHost,
        handle: PluginHandle,
        *,
        parent: PluginContext | None = None,
    ) -> None:
        self._host = host
        self._handle = handle
        self._parent = parent
        self._overlay: dict[str, Any] = {}

    # ── Properties ────────────────────────────────────────

    @property
    def plugin_id(self) -> str:
        return self._handle.entry_id

    @property
    def config(self) -> Any:
        return self._handle.config

    @property
    def parent(self) -> PluginContext | None:
        return self._parent

    # ── Services ──────────────────────────────────────────

    def get(self, service_name: str, default: Any = None) -> Any:
        """Look up service. Does NOT check inject (optional capability)."""
        if service_name in self._overlay:
            return self._overlay[service_name]
        return self._host.get_service(service_name, default)

    def require(self, service_name: str) -> Any:
        """Look up service. Fail if not in ``inject`` or unavailable."""
        if service_name not in self._handle.injected:
            raise PluginError(f"Plugin {self.plugin_id!r} must declare {service_name!r} in inject")
        sentinel = object()
        value = self.get(service_name, sentinel)
        if value is sentinel:
            raise DependencyUnavailable(
                f"Required service {service_name!r} not available for plugin {self.plugin_id!r}"
            )
        return value

    def mount(
        self,
        service_name: str,
        value: Any,
        *,
        check: Callable[[], bool] | None = None,
    ) -> Cleanup:
        """Mount a service. Cleanup auto-registered in handle effects."""
        self._host.provide(self._handle, service_name, value, check)

        def cleanup() -> None:
            record = self._host.get_service_record(service_name)
            if record is not None and record.owner_id == self._handle.entry_id:
                self._host.remove_service(service_name)
                self._handle.provided_services.discard(service_name)

        self._handle.effects.append((cleanup, EffectMeta(label=f'ctx.mount("{service_name}")')))
        return cleanup

    def set(self, service_name: str, value: Any) -> None:
        """Overwrite a service. Only the owning fiber may call."""
        record = self._host.get_service_record(service_name)
        if record is None:
            raise PluginError(f"cannot set {service_name!r} without prior mount")
        if record.owner_id != self._handle.entry_id:
            raise PluginError(f"cannot set {service_name!r}: owned by {record.owner_id!r}")
        record.value = value

    # ── Effects ───────────────────────────────────────────

    def effect(
        self,
        setup: Callable[[], Any],
        label: str = "anonymous",
    ) -> Cleanup:
        """Register a reversible side effect. setup() runs immediately."""
        if self._handle.state not in {PluginState.LOADING, PluginState.ACTIVE}:
            raise PluginError(f"Cannot register effect in {self._handle.state.value} state")
        meta = EffectMeta(label=label)
        result = setup()

        # Generator: yield multiple disposers
        if inspect.isgenerator(result) or inspect.isasyncgen(result):
            gen = result

            def gen_cleanup() -> None:
                with contextlib.suppress(Exception):
                    gen.close()

            self._handle.effects.append((gen_cleanup, meta))
            return gen_cleanup

        # Iterable of disposers
        if isinstance(result, Iterable) and not callable(result):
            cleanups = list(result)

            def iter_cleanup() -> None:
                for c in reversed(cleanups):
                    if callable(c):
                        c()

            self._handle.effects.append((iter_cleanup, meta))
            return iter_cleanup

        # Single disposer or None
        cleanup: Cleanup = result if callable(result) else (lambda: None)
        self._handle.effects.append((cleanup, meta))
        return cleanup

    # ── Events ────────────────────────────────────────────

    def on(
        self,
        event: str,
        callback: Listener,
        *,
        prepend: bool = False,
        global_: bool = False,
    ) -> Cleanup:
        """Register event listener; auto-cleaned on deactivation."""
        token = self._host.events.on(
            self.plugin_id,
            event,
            callback,
            prepend=prepend,
            global_=global_,
        )
        self._handle.listener_tokens.add(token)

        def cleanup() -> None:
            self._host.events.off(token)
            self._handle.listener_tokens.discard(token)

        self._handle.effects.append((cleanup, EffectMeta(label=f'ctx.on("{event}")')))
        return cleanup

    def once(self, event: str, callback: Listener, **kw: Any) -> Cleanup:
        """One-shot listener."""
        token_holder: list[tuple[str, int] | None] = [None]

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if token_holder[0] is not None:
                self._host.events.off(token_holder[0])
                self._handle.listener_tokens.discard(token_holder[0])
                token_holder[0] = None
            return callback(*args, **kwargs)

        token = self._host.events.on(
            self.plugin_id,
            event,
            wrapper,
            prepend=kw.get("prepend", False),
            global_=kw.get("global_", False),
        )
        token_holder[0] = token
        self._handle.listener_tokens.add(token)

        def cleanup() -> None:
            if token_holder[0] is not None:
                self._host.events.off(token_holder[0])
                self._handle.listener_tokens.discard(token_holder[0])
                token_holder[0] = None

        self._handle.effects.append((cleanup, EffectMeta(label=f'ctx.once("{event}")')))
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

    # ── Accessor / Mixin ──────────────────────────────────

    def accessor(
        self,
        name: str,
        *,
        get: Callable[[], Any],
        set: Callable[[Any], None] | None = None,
    ) -> Cleanup:
        """Define a computed property on this ctx."""
        self._handle._accessors[name] = {"get": get, "set": set}

        def cleanup() -> None:
            self._handle._accessors.pop(name, None)

        self._handle.effects.append((cleanup, EffectMeta(label=f'ctx.accessor("{name}")')))
        return cleanup

    def mixin(
        self,
        source: str | object,
        keys: list[str] | dict[str, str],
    ) -> Cleanup:
        """Forward service methods as ctx accessors."""
        entries = [(k, k) for k in keys] if isinstance(keys, list) else list(keys.items())
        cleanups: list[Cleanup] = []
        for source_key, ctx_key in entries:

            def make_getter(sk: str = source_key) -> Any:
                svc = self.get(source) if isinstance(source, str) else source
                return getattr(svc, sk)

            c = self.accessor(ctx_key, get=make_getter)
            cleanups.append(c)

        def cleanup() -> None:
            for c in cleanups:
                c()

        return cleanup

    # ── Child context ─────────────────────────────────────

    def child(
        self,
        *,
        key: str,
        values: Mapping[str, Any] | None = None,
    ) -> PluginContext:
        """Run-scoped sub-context with overlay shadow."""
        if not key:
            raise ValueError("child key is empty")
        child = PluginContext(self._host, self._handle, parent=self)
        if values:
            child._overlay.update(values)
        return child

    # ── Inject shorthand ──────────────────────────────────

    async def inject(
        self,
        deps: tuple[str, ...] | dict[str, Any],
        callback: Callable[..., Any],
    ) -> Any:
        """Create a sub-fiber for *callback* when *deps* are satisfied."""
        from lca.layer0_infra.plugin.kernel._handle import PluginHandle
        from lca.layer0_infra.plugin.kernel._lifecycle import reconcile
        from lca.layer0_infra.plugin.kernel._spec import PluginSpec

        dep_names = tuple(deps.keys()) if isinstance(deps, dict) else deps
        spec = PluginSpec(
            name=f"_inject_{self.plugin_id}",
            apply=lambda ctx, cfg: callback(ctx),
        )
        handle = PluginHandle(
            entry_id=f"{self.plugin_id}.__inject__",
            spec=spec,
            config=None,
            injected=dep_names,
        )
        self._host.register_handle(handle)
        await reconcile(self._host)
        return handle
