"""K3:cordis Context + Fiber 启动(ADR-0115 K3 + ADR-0111 修订)。

Public surface
--------------
- :func:`spawn_fiber` —— 注册一个 Fiber 到父 Context(供 plugin 装载)。
- :func:`run_kernel` —— 主入口:``ResolvedProfile`` → booted ``cordis.Context``。
- :func:`run_resolved_kernel` —— 已知 ``ResolvedProfile`` 的入口。
- :func:`stop_kernel` —— 优雅关停(``ctx.dispose()``)。
- :func:`install_compile_result` —— 把编译产物 provide 到 ctx(transport 用)。
- :func:`boot_entries` —— 程序化 entries 的入口。
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from cordis import Context

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
from lca.harness.profile.resolve import ResolvedProfile, resolve_entries, resolve_profile
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
    """主入口:从 profile path 启动 cordis Context。"""
    resolved = resolve_profile(profile_path)
    return await run_resolved_kernel(resolved, bootstrap_file_store=bootstrap_file_store)


async def run_resolved_kernel(
    resolved: ResolvedProfile,
    *,
    bootstrap_file_store: FileStore | None = None,
) -> Context:
    """Boot an already-resolved profile through the production lifecycle."""
    products = compile_profile_boot_products(resolved)
    return await _boot_context(products, bootstrap_file_store=bootstrap_file_store)


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
    """Boot one prepared plugin sequence with a single audited lifecycle seam."""
    resolved = products.resolved_profile
    if resolved is None:
        raise StageError(Stage.BOOT, "Profile boot requires a resolved profile")
    ctx = Context()
    try:
        for entry in BootEntry.from_resolved(resolved):
            spawn_fiber(ctx, entry.definition, entry.config)
            await _await_fiber_for(ctx, entry.definition.spec.id)
            if entry.definition.id == "lca-file-store-service" and bootstrap_file_store is not None:
                _bind_bootstrap_file_store(ctx, bootstrap_file_store)
        attach_profile_boot_products(ctx, products)
        install_observability(ctx)
    except BaseException:
        await _dispose_context(ctx)
        raise
    return ctx


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
