"""Boot a harness plugin tree from a profile YAML (ADR-0061 / ADR-0062).

Public API:
  - ``resolve_profile`` / ``boot_resolved_profile`` — two-phase model
  - ``boot_profile`` — compat façade (resolve then boot)
  - ``load_profile_entries`` / ``boot_entries`` — retained for tests that
    assemble entry dicts without a profile file; ``boot_entries`` still
    goes through Manifest validation when modules declare ``@plugin``.

Lifecycle is owned by vendored Cordis: ``ctx.registry.plugin(...)`` returns
a :class:`cordis.fiber.Fiber` per plugin, and ``await ctx.dispose()``
runs all fiber effects in reverse-registration order. This module only
bridges LCA's "shared parent ctx + Manifest-audited plugin" model into
that lifecycle; it does NOT maintain its own ``started[]`` / disposer
list (ADR-0062 §4).
"""

from __future__ import annotations

import contextlib

# === Deprecation (ADR-0115) ===
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cordis import Context

from lca.harness.plugin_api import AuditedPluginContext, PluginDefinition
from lca.harness.profile.boot_products import (
    ProfileBootProducts,
    attach_profile_boot_products,
    compile_profile_boot_products,
)
from lca.harness.profile.boot_projection import BootEntry
from lca.harness.profile.resolve import (
    ProfileResolveError,
    ResolvedProfile,
    dump_resolved,
    resolve_entries,
    resolve_profile,
)
from lca.harness.profile.source import load_profile_entries
from lca.infrastructure.file_store import FileStore

warnings.warn(
    "lca.harness.profile.boot is deprecated, use lca_kernel.boot (ADR-0115)",
    DeprecationWarning,
    stacklevel=2,
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
    """Preflight and boot one resolved plugin graph through the shared sequence.

    The immutable Profile boot products are compiled before a ``Context`` or
    Fiber lifecycle exists. A malformed runtime closure therefore fails closed
    without invoking any plugin setup; after the preflight succeeds, the shared
    lifecycle module is the only place that turns a manifest definition into a
    Cordis Fiber, attaches the boot products, handles failed boot, and installs
    observability. Keeping this interface small prevents the two supported
    inputs from drifting into different audit semantics.
    """
    products = compile_profile_boot_products(resolved)
    return await _boot_context(products, bootstrap_file_store=bootstrap_file_store)


async def boot_entries(
    entries: list[dict[str, Any]],
    *,
    bootstrap_file_store: FileStore | None = None,
) -> Context:
    """Boot programmatic declarations through the production Resolve semantics.

    This compatibility adapter only supplies in-memory input. Manifest identity,
    configuration validation, provider ownership, layer ordering, and DAG
    construction are all resolved before the shared Fiber lifecycle executes, so
    a test fixture cannot develop a second plugin-loading dialect. The resolved
    graph is attached through the same boot-products seam used by production
    boot; runtime closure remains the responsibility of explicit capability-read
    fixtures and is not compiled here.
    """
    resolved = resolve_entries(entries)
    return await _boot_context(
        ProfileBootProducts(resolved_profile=resolved),
        bootstrap_file_store=bootstrap_file_store,
    )


def _install_observability(ctx: Context) -> None:
    """Boot 末尾唯一挂点：把各 seam registry 装配成 BoundObservability。

    Assemble 必须 boot 期发生一次；run 期业务代码通过
    ``ctx.inject("observability")`` 拿到 Bound，再按需为 run 边追加
    jsonl/tail 等 writer projection。Facade（record/span/annotate/score）
    经 ContextVar ``lca_observability_bound`` 取当前激活的 Bound，与
    boot ctx 解耦。
    """
    from lca.harness.observability import assemble_observability
    from lca.infrastructure.observability import ObservabilitySettings

    assemble_observability(ctx, ObservabilitySettings())


async def boot_profile(
    profile_path: Path | str,
    *,
    bootstrap_file_store: FileStore | None = None,
) -> Context:
    """Resolve then boot, optionally binding a Gateway-owned FileStore."""
    resolved = resolve_profile(profile_path)
    return await boot_resolved_profile(resolved, bootstrap_file_store=bootstrap_file_store)


# ── Helpers ─────────────────────────────────────────────────────────


async def _boot_context(
    products: ProfileBootProducts,
    *,
    bootstrap_file_store: FileStore | None = None,
) -> Context:
    """Boot one prepared plugin sequence with a single audited lifecycle seam.

    Both public entrances converge here after their input adapters have done
    their work. The sequence owns only common mechanics: Fiber-backed setup,
    boot-product attachment, partial-context cleanup, and observability
    assembly. Inspection and composition then read the attached products
    instead of guessing Context attribute names.
    """
    resolved = products.resolved_profile
    if resolved is None:
        raise RuntimeError("Profile boot requires a resolved profile")
    ctx = Context()
    try:
        for entry in BootEntry.from_resolved(resolved):
            await _boot_plugin(ctx, entry.definition, entry.config)
            if entry.definition.id == "lca-file-store-service" and bootstrap_file_store is not None:
                _bind_bootstrap_file_store(ctx, bootstrap_file_store)
        attach_profile_boot_products(ctx, products)
        _install_observability(ctx)
    except BaseException:
        await _dispose_context(ctx)
        raise
    return ctx


def _bind_bootstrap_file_store(ctx: Context, store: FileStore | None) -> None:
    """Register the app-owned store before ordinary FileStore providers boot.

    The kernel/transport boundary is profile-agnostic: if the active
    profile does not wire the ``file_store`` seam (``lca-file-store-service``
    plugin), the argument is silently ignored. This lets the lifespan
    accept a bootstrap store without coupling to a specific capability
    plugin being present.
    """
    if store is None:
        return
    from lca.infrastructure.capability.files import FileStoreService

    try:
        service = ctx.inject("file_store")
    except KeyError:
        return
    if not isinstance(service, FileStoreService):
        return
    service.register("webserver_bootstrap", store, activate=True)


async def _boot_plugin(ctx: Context, definition: PluginDefinition, config: Any) -> None:
    """Run one manifest plugin once through its Cordis Fiber.

    ``ResolvedProfile`` already supplies a validated topological order. The
    callback therefore runs against the shared composition context, not the
    Fiber's child context: sibling plugins retain the existing one-scope
    lookup semantics, while Fiber remains the sole owner of execution,
    returned disposers, and reverse-order cleanup.
    """

    audits: list[AuditedPluginContext] = []

    async def setup(_fiber_ctx: Context, fiber_config: Any) -> Any:
        audited = AuditedPluginContext(ctx, definition)
        audits.append(audited)
        return await _run_setup(definition.setup, audited, fiber_config)

    fiber = ctx.registry.plugin(
        {
            "name": definition.spec.id,
            "apply": setup,
            # Dependency order was validated during Resolve. Cordis child
            # contexts scope provides locally, whereas the harness composes
            # capabilities on the shared parent scope; do not apply a second,
            # incompatible DI gate here.
            "inject": [],
            "Config": definition.Config,
        },
        config=config,
    )
    # Cordis registers the Fiber under the root Fiber, while harness callers
    # own the root Context. Bridge those lifecycles so ctx.dispose() unloads
    # every plugin in reverse boot order and runs each returned disposer.
    ctx.effect(fiber.dispose, label=f"plugin:{definition.spec.id}")
    await fiber.await_()

    if len(audits) != 1:
        raise RuntimeError(f"plugin {definition.spec.id}: expected exactly one audited setup")
    _validate_audited_interactions(definition, audits[0])


def _validate_audited_interactions(
    definition: PluginDefinition, audited: AuditedPluginContext
) -> None:
    """Defend the declaration-to-interaction subset invariant after Fiber boot."""

    from lca.harness.plugin_context import requirement_covers_key

    declared_provide = set(definition.provided_capability_keys)
    declared_require = set(definition.required_capability_keys)
    undeclared_provide = audited.provided - declared_provide
    # Concrete keys collected via require_matching("field_producer.") are
    # covered by a declared ``field_producer.*`` wildcard — same rule as
    # AuditedPluginContext.require(allow_wildcard=True).
    undeclared_require = {
        key
        for key in audited.required
        if key not in declared_require
        and not any(requirement_covers_key(pattern, key) for pattern in declared_require)
    }
    if undeclared_provide or undeclared_require:
        raise ProfileResolveError(
            f"plugin {definition.spec.id}: undeclared interaction "
            f"provide={sorted(undeclared_provide)} "
            f"require={sorted(undeclared_require)}"
        )


async def _run_setup(setup_fn: Callable[..., Any], ctx: Any, config: Any) -> Any:
    """Invoke setup() and await if it returned a coroutine."""
    result = setup_fn(ctx, config)
    if hasattr(result, "__await__"):
        return await result
    return result


async def _dispose_context(ctx: Context) -> None:
    """Run ctx.dispose() and swallow its errors so the caller can re-raise
    the original startup exception.

    Cordis's :meth:`Context.dispose` already logs individual disposer
    failures and continues. Any remaining error is non-fatal here; the
    caller (boot_resolved_profile / boot_entries) is about to re-raise
    the original startup error anyway.
    """
    with contextlib.suppress(BaseException):
        await ctx.dispose()
