"""COMPAT shim — kernel boot is the single production entry (ADR-0195 P4-K02).

Public boot APIs forward to :mod:`lca_kernel.boot`. Resolve helpers
(``resolve_profile``, ``load_profile_entries``) remain here for harness
composition; new callers should prefer ``lca_kernel.run_kernel``.

# COMPAT(owner: ADR-0195 P4-K02, from: lca.harness.profile.boot.boot,
# to: lca_kernel.run_kernel / run_resolved_kernel / boot_entries,
# delete_when: rg "from lca\\.harness\\.profile\\.boot" lca/ scripts/ = 0
#   (tests/ excluded — migration tracked in P4-K03),
# forbidden_new_usage: 禁止在本模块新增 boot 逻辑; 新代码 import lca_kernel)
"""

from __future__ import annotations

import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cordis import Context

from lca.harness.plugin_api import AuditedPluginContext, PluginDefinition
from lca.harness.profile.resolve.resolve import (
    ProfileResolveError,
    ResolvedProfile,
    dump_resolved,
    resolve_profile,
)
from lca.harness.profile.resolve.source import load_profile_entries
from lca.infrastructure.file.store import FileStore

_DEPRECATION = (
    "lca.harness.profile.boot.{fn} is deprecated; "
    "use lca_kernel.{kernel_fn} (ADR-0195 P4-K02)"
)


def _warn(fn: str, kernel_fn: str) -> None:
    warnings.warn(
        _DEPRECATION.format(fn=fn, kernel_fn=kernel_fn),
        DeprecationWarning,
        stacklevel=3,
    )


__all__ = [
    "ProfileResolveError",
    "ResolvedProfile",
    "boot_entries",
    "boot_profile",
    "boot_resolved_profile",
    "dump_resolved",
    "load_profile_entries",
    "resolve_profile",
]


async def boot_resolved_profile(
    resolved: ResolvedProfile,
    *,
    bootstrap_file_store: FileStore | None = None,
) -> Context:
    """Preflight and boot one resolved plugin graph through the kernel boot seam."""
    _warn("boot_resolved_profile", "run_resolved_kernel")
    from lca_kernel.boot.boot import run_resolved_kernel

    return await run_resolved_kernel(resolved, bootstrap_file_store=bootstrap_file_store)


async def boot_entries(
    entries: list[dict[str, Any]],
    *,
    bootstrap_file_store: FileStore | None = None,
) -> Context:
    """Boot programmatic declarations through the production Resolve semantics."""
    _warn("boot_entries", "boot_entries")
    from lca_kernel.boot.boot import boot_entries as kernel_boot_entries

    return await kernel_boot_entries(entries, bootstrap_file_store=bootstrap_file_store)


async def boot_profile(
    profile_path: Path | str,
    *,
    bootstrap_file_store: FileStore | None = None,
) -> Context:
    """Resolve then boot, optionally binding a Gateway-owned FileStore."""
    _warn("boot_profile", "run_kernel")
    from lca_kernel import run_kernel

    return await run_kernel(profile_path, bootstrap_file_store=bootstrap_file_store)


# ── Fiber lifecycle helpers (tests + boot-time interaction audit) ─────


async def _boot_plugin(ctx: Context, definition: PluginDefinition, config: Any) -> None:
    """Run one manifest plugin once through its Cordis Fiber (test helper)."""

    audits: list[AuditedPluginContext] = []

    async def setup(_fiber_ctx: Context, fiber_config: Any) -> Any:
        audited = AuditedPluginContext(ctx, definition)
        audits.append(audited)
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
    await fiber.await_()

    if len(audits) != 1:
        raise RuntimeError(f"plugin {definition.spec.id}: expected exactly one audited setup")
    _validate_audited_interactions(definition, audits[0])


def _validate_audited_interactions(
    definition: PluginDefinition, audited: AuditedPluginContext
) -> None:
    """Defend the declaration-to-interaction subset invariant after Fiber boot."""

    from lca.harness.plugin.context import requirement_covers_key

    declared_provide = set(definition.provided_capability_keys)
    declared_require = set(definition.required_capability_keys)
    undeclared_provide = audited.provided - declared_provide
    registered_seams = {seam for seam, _ in audited.registered}
    missing_provide = {
        key
        for key in (declared_provide - audited.provided)
        if "[" not in key
        and key not in registered_seams
        and not any(key.startswith(seam + ".") for seam in registered_seams)
        and not any(key.startswith(req + ".") for req in audited.required)
    }
    undeclared_require = {
        key
        for key in audited.required
        if key not in declared_require
        and not any(requirement_covers_key(pattern, key) for pattern in declared_require)
    }
    if undeclared_provide or undeclared_require or missing_provide:
        raise ProfileResolveError(
            f"plugin {definition.spec.id}: undeclared interaction "
            f"provide={sorted(undeclared_provide)} "
            f"require={sorted(undeclared_require)} "
            f"missing_provide={sorted(missing_provide)}"
        )


async def _run_setup(setup_fn: Callable[..., Any], ctx: Any, config: Any) -> Any:
    """Invoke setup() and await if it returned a coroutine."""
    result = setup_fn(ctx, config)
    if hasattr(result, "__await__"):
        return await result
    return result
