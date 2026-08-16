"""Lifecycle driver — reconcile + activate + deactivate.

The **brain** of the plugin runtime. Drives the state machine:
- ``reconcile(host)`` — convergence loop: activate every handle whose
  dependencies are satisfied, until stable state or cycle detected.
- ``activate(host, handle)`` — validate config → run apply → ACTIVE.
- ``deactivate(host, handle)`` — run all effect disposers LIFO,
  remove owned services, cascade to dependents.

This module imports host, context, and handle — it is the convergence
point where all kernel pieces connect. It owns NO data itself; it only
reads/writes through the host.

Mirrors the ``_reconcile`` / ``_activate`` / ``_deactivate`` methods
from DSH Cordis, extracted into a standalone driver.
"""

from __future__ import annotations

import inspect
from typing import Any

from lca.layer0_infra.plugin.kernel._context import PluginContext
from lca.layer0_infra.plugin.kernel._effect_meta import EffectMeta
from lca.layer0_infra.plugin.kernel._handle import PluginHandle
from lca.layer0_infra.plugin.kernel._host import PluginHost
from lca.layer0_infra.plugin.kernel._types import (
    PluginError,
    PluginState,
)

# ── Public API ────────────────────────────────────────────


async def reconcile(host: PluginHost) -> None:
    """Convergence loop: activate every PENDING handle whose deps are met.

    Repeats until no more progress can be made. After termination:
    - All satisfiable plugins are ACTIVE.
    - Unsatisfiable plugins remain PENDING (missing deps or cycle).
    """
    while True:
        progressed = False
        for handle in list(host.handles.values()):
            if not handle.desired or handle.state is not PluginState.PENDING:
                continue
            if not _deps_ready(host, handle):
                continue
            await activate(host, handle)
            progressed = True
        if not progressed:
            break


async def activate(host: PluginHost, handle: PluginHandle) -> None:
    """Activate one plugin: validate config → apply → ACTIVE.

    On failure: dispose any effects registered during apply,
    remove owned services, mark FAILED.
    """
    if handle.state is not PluginState.PENDING or not handle.desired:
        return
    if not _deps_ready(host, handle):
        return

    handle.state = PluginState.LOADING
    await host.events.emit("internal/status", handle, PluginState.PENDING)

    context = PluginContext(host, handle)

    try:
        config = _validate_config(handle)
        handle.config = config

        mounted_value: Any = None

        if handle.spec.is_class:
            # Constructor shape: instantiate Service subclass
            instance = handle.spec.apply(context, config)
            mounted_value = instance
            if hasattr(instance, "init"):
                init_result = instance.init()
                if inspect.isgenerator(init_result):
                    for disposer in init_result:
                        handle.effects.append((disposer, EffectMeta(label="[Service.init]")))
                elif inspect.isasyncgen(init_result):
                    async for disposer in init_result:
                        handle.effects.append((disposer, EffectMeta(label="[Service.init]")))
        else:
            # Function/object shape: call apply directly
            result = handle.spec.apply(context, config)
            if inspect.isawaitable(result):
                result = await result
            if inspect.isgenerator(result):
                for disposer in result:
                    handle.effects.append((disposer, EffectMeta(label="yield")))
            elif inspect.isasyncgen(result):
                async for disposer in result:
                    handle.effects.append((disposer, EffectMeta(label="yield")))
            elif result is not None and callable(result):
                handle.effects.append((result, EffectMeta(label="return")))

        handle.state = PluginState.ACTIVE
        handle.error = None

        # Auto-mount: if plugin declares ``provides`` but didn't mount
        # during apply, mount the module/instance itself under that key.
        spec = handle.spec
        if spec.provides is not None and host.get_service(spec.provides) is None:
            context.mount(spec.provides, mounted_value or handle.spec.apply)

        await host.events.emit("internal/status", handle, PluginState.LOADING)
        await host.events.emit("internal/plugin.active", handle)

    except BaseException as exc:
        handle.error = exc
        await _run_effects(handle)
        host.remove_owned_services(handle)
        handle.state = PluginState.FAILED
        await host.events.emit("internal/status", handle, PluginState.LOADING)
        await host.events.emit("internal/plugin.failed", handle, exc)


async def deactivate(host: PluginHost, handle: PluginHandle, *, permanent: bool) -> None:
    """Deactivate one plugin: run disposers → remove services → cascade.

    If ``permanent=True``, mark DISPOSED. Otherwise back to PENDING
    (allows re-activation when dependencies return).

    Cascading: if this handle provided services that other ACTIVE
    handles depend on, those consumers are also deactivated.
    """
    if handle.state in {PluginState.DISPOSED, PluginState.PENDING}:
        if permanent:
            handle.state = PluginState.DISPOSED
        return
    if handle.state is PluginState.UNLOADING:
        return

    old_state = handle.state
    handle.state = PluginState.UNLOADING
    await host.events.emit("internal/status", handle, old_state)

    # 1. Remove services this handle owns
    removed_names = host.remove_owned_services(handle)

    # 2. Run all effect disposers (LIFO)
    await _run_effects(handle)

    # 3. Set final state
    handle.error = None
    handle.state = PluginState.DISPOSED if permanent else PluginState.PENDING
    await host.events.emit("internal/status", handle, PluginState.UNLOADING)
    await host.events.emit("internal/plugin.disposed", handle)

    # 4. Cascade: deactivate consumers that depended on our services
    if removed_names:
        await _cascade_deactivate(host, handle, removed_names)


async def shutdown(host: PluginHost) -> None:
    """Deactivate all handles in reverse registration order."""
    for handle in reversed(list(host.handles.values())):
        handle.desired = False
        await deactivate(host, handle, permanent=True)


# ── Config validation ─────────────────────────────────────


def _validate_config(handle: PluginHandle) -> Any:
    """Validate handle.config against the plugin's Config schema."""
    config = handle.config
    if handle.spec.validate is not None:
        return handle.spec.validate(config)
    # Look for Config class on the spec's source module
    # Default: pass through as-is if no validator
    return config


# ── Dependency check ──────────────────────────────────────


def _deps_ready(host: PluginHost, handle: PluginHandle) -> bool:
    """True if all of handle's injected deps are available."""
    return all(host.get_service(name, None) is not None for name in handle.dependencies)


# ── Effect disposal ───────────────────────────────────────


async def _run_effects(handle: PluginHandle) -> None:
    """Run all effect disposers in LIFO order. Suppress individual errors."""
    import structlog

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

    if errors:
        structlog.get_logger("lca.plugin").warning(
            "effect_dispose_errors",
            entry_id=handle.entry_id,
            count=len(errors),
        )


# ── Cascade ───────────────────────────────────────────────


async def _cascade_deactivate(
    host: PluginHost,
    source: PluginHandle,
    removed_names: list[str],
) -> None:
    """Deactivate ACTIVE consumers that depend on any of *removed_names*."""
    removed_set = set(removed_names)
    for consumer in list(host.handles.values()):
        if consumer is source or consumer.state is not PluginState.ACTIVE:
            continue
        if any(dep in removed_set for dep in consumer.dependencies):
            await deactivate(host, consumer, permanent=False)


# ── Config update with rollback ───────────────────────────


async def update_config(host: PluginHost, entry_id: str, new_config: Any) -> PluginHandle:
    """Update a plugin's config with transactional rollback on failure.

    1. Save old config.
    2. Deactivate (non-permanent).
    3. Set new config, reconcile.
    4. If ACTIVE → done.
    5. If FAILED → restore old config, reconcile again, raise.
    """
    handle = host.handles[entry_id]
    old_config = handle.config

    if not handle.desired:
        handle.config = new_config
        return handle

    await deactivate(host, handle, permanent=False)
    handle.config = new_config
    handle.error = None
    await reconcile(host)

    if handle.state is PluginState.ACTIVE:
        return handle

    # Rollback
    failure = handle.error or PluginError(f"Plugin {entry_id!r} failed to recover")
    await deactivate(host, handle, permanent=False)
    handle.config = old_config
    handle.error = None
    await reconcile(host)
    raise PluginError(f"Plugin {entry_id!r} config update failed, rolled back") from failure
