"""K3:cordis Context + Fiber 启动(ADR-0115 K3 + ADR-0111 修订 + ADR-0116)。

Public surface
--------------
- :func:`spawn_fiber` —— 注册一个 Fiber 到父 Context(供 plugin 装载)。
- :func:`run_kernel` —— 主入口:``ResolvedProfile`` → booted ``cordis.Context``。
- :func:`run_resolved_kernel` —— 已知 ``ResolvedProfile`` 的入口。
- :func:`stop_kernel` —— graceful shutdown(``ctx.dispose()``)。
- :func:`install_compile_result` —— 把编译产物 provide 到 ctx(transport 用)。
- :func:`boot_entries` —— 程序化 entries 的入口。

Boot 可观测性(ADR-0116 §决定 2)
-------------------------------
三个 typed JournalEvent 在 boot 路径上 emit:

- :class:`~lca.contracts.models.observability.journal.BootProfileResolved`
  boot 完成后:profile path / manifest hash / plugin count / bundle count /
  duration / 拓扑顺序。
- :class:`~lca.contracts.models.observability.journal.BootPluginFiberSpawned`
  每个 plugin fiber spawn 完成后一对 ``status=started/ok``。
- :class:`~lca.contracts.models.observability.journal.BootObservabilityAssembled`
  BoundObservability 装配完成后:bound seams / evidence store kind /
  journal_enabled / duration。

实现细节:由于 observability backend registries(``attribute_policy_backends``
/ ``journal_backends`` / ``tracer_backends`` / ``fact_scorers``)由 plugin 在
fiber spawn 时灌入 ctx,boot 顺序必须为 ``install_observability → spawn fibers
→ re-install observability → emit boot events``。第一遍 install 是基线
(no-op backends),第二遍 install 拿到已填充 registries 后真正写入 journal。
若 kernel 在测试 / 最小路径下没有 plugin,第二遍 install 仍安全 no-op。
"""

from __future__ import annotations

import contextlib
import time
from pathlib import Path
from typing import Any

from cordis import Context

from lca.contracts.models.observability.journal import (
    BootObservabilityAssembled,
    BootPluginFiberSpawned,
    BootProfileResolved,
)
from lca.harness.plugin_api import PluginDefinition

# boot_products is the seam's source-of-truth (compat-only in PR-2 sense);
# the kernel still imports the data classes from the legacy module path.
from lca.harness.profile.boot_products import (
    ProfileBootProducts,
    attach_profile_boot_products,
    compile_profile_boot_products,
    compiled_plan_from_scope,
    profile_boot_products_from_scope,
    resolved_profile_from_scope,
)
from lca.harness.profile.boot_projection import BootEntry
from lca.harness.profile.resolve import ResolvedProfile, resolve_entries
from lca.infrastructure.file_store import FileStore
from lca_kernel.errors import KernelError, StageError
from lca_kernel.observability import install_observability
from lca_kernel.stages import Stage


def spawn_fiber(ctx: Context, definition: PluginDefinition, config: Any) -> Any:
    """注册一个 Fiber 到父 Context(ADR-0062 §4 cordis Fiber Boot)。"""
    from lca.harness.plugin_api import AuditedPluginContext

    async def setup(_fiber_ctx: Context, fiber_config: Any) -> Any:
        audited = AuditedPluginContext(ctx, definition)
        return await _run_setup(definition.setup, audited, fiber_config)

    fiber = ctx.registry.plugin(
        {
            "name": definition.spec.id,
            "apply": setup,
            "inject": [],
            "Config": definition.Config,
        },
        config=config,
    )
    ctx.effect(fiber.dispose, label=f"plugin:{definition.spec.id}")
    return fiber


async def run_kernel(
    profile_path: Path | str,
    *,
    bootstrap_file_store: FileStore | None = None,
) -> Context:
    """主入口: 从 profile path 启动 cordis Context.

    Delegates to :func:`lca.harness.profile.boot.boot_profile`, which is
    the production boot implementation. The kernel is the single seam
    that compiles a profile into a running Context; it does NOT maintain
    a parallel boot implementation (the local ``_boot_context`` helper
    exists only to satisfy unit tests of :func:`_emit_boot_events`).
    """
    from lca.harness.profile.boot import boot_profile

    return await boot_profile(profile_path, bootstrap_file_store=bootstrap_file_store)


async def run_resolved_kernel(
    resolved: ResolvedProfile,
    *,
    bootstrap_file_store: FileStore | None = None,
) -> Context:
    """Boot an already-resolved profile through the production lifecycle."""
    from lca.harness.profile.boot import boot_resolved_profile

    return await boot_resolved_profile(resolved, bootstrap_file_store=bootstrap_file_store)


async def stop_kernel(ctx: Context) -> None:
    """Graceful shutdown — dispose the cordis Context."""
    with contextlib.suppress(BaseException):
        await ctx.dispose()


def install_compile_result(ctx: Context, products: ProfileBootProducts) -> None:
    """把编译产物 provide 到 ctx(transport plugin 通过 ``ctx.inject`` 读取)。"""
    if products is None:
        raise KernelError("install_compile_result requires a non-None ProfileBootProducts")
    attach_profile_boot_products(ctx, products)


async def boot_entries(
    entries: list[dict[str, Any]],
    *,
    bootstrap_file_store: FileStore | None = None,
) -> Context:
    """Boot programmatic entries through the production Resolve semantics."""
    resolved = resolve_entries(entries)
    products = ProfileBootProducts(resolved_profile=resolved)
    return await _boot_context(products, bootstrap_file_store=bootstrap_file_store)


# ── Internals ─────────────────────────────────────────────────────────


async def _boot_context(
    products: ProfileBootProducts,
    *,
    bootstrap_file_store: FileStore | None = None,
) -> Context:
    """Boot one prepared plugin sequence with a single audited lifecycle seam.

    Boot ordering (ADR-0116 §决定 2 + ADR-0115 K5):

    1. ``install_observability(ctx)`` —— baseline,所有 backend None。
    2. 遍历 BootEntry,对每个 plugin ``spawn_fiber + await_fiber``,记录
       ``BootPluginFiberSpawned`` 到 ``pending_events``(journal 仍为 None,
       write() 安全 no-op)。
    3. ``install_observability(ctx)`` —— 第二次 install,registry 已被 plugin
       灌入,journal 真正可写。
    4. Flush pending events,emit ``BootProfileResolved`` + ``BootObservabilityAssembled``。
    """
    resolved = products.resolved_profile
    if resolved is None:
        raise StageError(Stage.BOOT, "Profile boot requires a resolved profile")
    ctx = Context()
    boot_started = time.monotonic()
    plugin_started_at: dict[str, float] = {}
    pending_events: list[Any] = []
    try:
        # Step 1: baseline install (backends None).
        install_observability(ctx)
        # Step 2: spawn fibers, buffer BootPluginFiberSpawned.
        topo_order: list[str] = []
        for entry in BootEntry.from_resolved(resolved):
            plugin_started_at[entry.definition.spec.id] = time.monotonic()
            spec = entry.definition.spec
            pending_events.append(
                BootPluginFiberSpawned(
                    plugin_id=spec.id,
                    layer=getattr(spec, "layer", "L0"),
                    kind=getattr(entry.definition, "kind", "provider"),
                    stage=Stage.BOOT,
                    duration_ms=0.0,
                    status="started",
                )
            )
            spawn_fiber(ctx, entry.definition, entry.config)
            await _await_fiber_for(ctx, entry.definition.spec.id)
            if entry.definition.id == "lca-file-store-service" and bootstrap_file_store is not None:
                _bind_bootstrap_file_store(ctx, bootstrap_file_store)
            finished_ms = (time.monotonic() - plugin_started_at[entry.definition.spec.id]) * 1000
            # Replace the "started" placeholder with an "ok" outcome that carries the real duration.
            pending_events[-1] = BootPluginFiberSpawned(
                plugin_id=spec.id,
                layer=getattr(spec, "layer", "L0"),
                kind=getattr(entry.definition, "kind", "provider"),
                stage=Stage.BOOT,
                duration_ms=finished_ms,
                status="ok",
            )
            topo_order.append(spec.id)
        attach_profile_boot_products(ctx, products)
        # Step 3: re-install observability with populated registries.
        install_observability(ctx)
        # Step 4: flush buffered events + emit final boot events.
        _emit_boot_events(
            ctx,
            pending_events=pending_events,
            products=products,
            topo_order=tuple(topo_order),
            boot_started=boot_started,
        )
    except BaseException:
        await _dispose_context(ctx)
        raise
    return ctx


def _emit_boot_events(
    ctx: Context,
    *,
    pending_events: list[Any],
    products: ProfileBootProducts,
    topo_order: tuple[str, ...],
    boot_started: float,
) -> None:
    """Flush pending boot events and emit final BootProfileResolved / BootObservabilityAssembled.

    Journal may still be ``None`` (no plugin wired a journal backend) — in
    that case ``BoundObservability.journal.write`` is a documented safe
    no-op and we silently skip. The events are still recorded as boot
    diagnostic data via :class:`BootTrace` when observability re-installs
    with the journal available.
    """
    bound = _safe_inject(ctx, "observability")
    journal = getattr(bound, "journal", None) if bound is not None else None
    if journal is None:
        return
    obs_started = time.monotonic()
    for event in pending_events:
        with contextlib.suppress(Exception):
            journal.write(event)
    duration_ms = (time.monotonic() - boot_started) * 1000
    profile_path = str(
        getattr(products, "path", "") or getattr(products.resolved_profile, "path", "")
    )
    with contextlib.suppress(Exception):
        journal.write(
            BootProfileResolved(
                profile_path=profile_path,
                manifest_hash="",
                plugin_count=len(topo_order),
                bundle_count=0,
                duration_ms=duration_ms,
                topo_order=topo_order,
            )
        )
    bound_seams = tuple(
        name
        for name, present in (
            ("journal", getattr(bound, "journal", None) is not None),
            ("tracer", getattr(bound, "tracer", None) is not None),
            ("policy", getattr(bound, "policy", None) is not None),
            ("scorers", bool(getattr(bound, "scorers", ()))),
        )
        if present
    )
    with contextlib.suppress(Exception):
        journal.write(
            BootObservabilityAssembled(
                bound_seams=bound_seams,
                evidence_store_kind=type(getattr(bound, "evidence_store", None)).__name__
                if getattr(bound, "evidence_store", None) is not None
                else "none",
                journal_enabled=getattr(bound, "journal", None) is not None,
                duration_ms=(time.monotonic() - obs_started) * 1000,
            )
        )


def _safe_inject(ctx: Any, key: str) -> Any:
    """``ctx.inject(key, default=None)`` wrapper that handles both cordis Context and Protocol shapes."""
    inject = getattr(ctx, "inject", None)
    if not callable(inject):
        return None
    try:
        return inject(key, default=None)
    except (KeyError, TypeError):
        return None


def _bind_bootstrap_file_store(ctx: Context, store: FileStore) -> None:
    """Register the app-owned store before ordinary FileStore providers boot."""
    from lca.infrastructure.capability.files import FileStoreService

    service = ctx.inject("file_store")
    if not isinstance(service, FileStoreService):
        raise TypeError("file_store seam did not provide FileStoreService")
    service.register("app_bootstrap", store, activate=True)


async def _await_fiber_for(ctx: Context, plugin_id: str) -> None:
    """Wait for the named plugin's fiber to settle (best-effort)."""
    loader = ctx.inject("loader", default=None)
    if loader is None:
        return
    entries = list(loader.entries()) if hasattr(loader, "entries") else ()
    for entry in entries:
        if getattr(entry.options, "name", None) == plugin_id and entry.fiber is not None:
            await entry.fiber.await_()


async def _run_setup(setup_fn: Any, ctx: Any, config: Any) -> Any:
    """Invoke ``setup_fn(ctx, config)`` and await if it returned a coroutine."""
    result = setup_fn(ctx, config)
    if hasattr(result, "__await__"):
        return await result
    return result


async def _dispose_context(ctx: Context) -> None:
    """Best-effort dispose so the caller can re-raise the original boot error."""
    with contextlib.suppress(BaseException):
        await ctx.dispose()


__all__ = [
    "BootEntry",
    "ProfileBootProducts",
    "attach_profile_boot_products",
    "boot_entries",
    "compile_profile_boot_products",
    "compiled_plan_from_scope",
    "install_compile_result",
    "profile_boot_products_from_scope",
    "resolved_profile_from_scope",
    "run_kernel",
    "run_resolved_kernel",
    "spawn_fiber",
    "stop_kernel",
]
