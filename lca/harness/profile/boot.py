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
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cordis import Context

from lca.harness.plugin_api import AuditedPluginContext
from lca.harness.profile.entry_loader import prepare_entries
from lca.harness.profile.resolve import (
    ProfileResolveError,
    ResolvedProfile,
    dump_resolved,
    resolve_profile,
)

if TYPE_CHECKING:
    from cordis.fiber import Fiber

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


def load_profile_entries(profile_path: Path | str) -> list[dict[str, Any]]:
    """Expand bundles + patch into entry dicts (compat for dump-profile / tests).

    Prefer :func:`resolve_profile` for validated Manifest-aware resolution.
    """
    resolved = resolve_profile(profile_path)
    entries: list[dict[str, Any]] = []
    for item in resolved.plugins:
        config = item.config
        if hasattr(config, "model_dump"):
            config = config.model_dump(mode="python")
        entry: dict[str, Any] = {
            "id": item.id,
            "$module": item.module,
            "config": config if isinstance(config, dict) else {},
        }
        if item.disabled:
            entry["disabled"] = True
        entries.append(entry)
    return entries


async def boot_resolved_profile(resolved: ResolvedProfile) -> Context:
    """Execute phase: setup plugins in DAG order under audited PluginContext.

    Each plugin gets a Cordis :class:`Fiber` (via ``ctx.registry.plugin``)
    so its effect/dispose lifecycle is owned by the container. If any
    plugin's ``setup()`` raises, we dispose the partial Context and
    aggregate the startup error with any cleanup errors via
    :class:`BaseExceptionGroup` so neither vanishes (ADR-0062 §4).
    """
    ctx = Context()
    fibers: list[Fiber] = []
    loaded: list[_EntryView] = []

    try:
        for item in resolved.plugins:
            if item.disabled:
                continue
            # Fiber owns the plugin's effect/dispose lifecycle; we only
            # use it as a registration handle because setup() must run
            # against the audited parent ctx (LCA's per-plugin audited
            # context, NOT the fiber's child ctx).
            fiber = ctx.registry.plugin(item.definition.setup, config=item.config)
            fibers.append(fiber)
            audited = AuditedPluginContext(_inner=ctx, _definition=item.definition)
            try:
                result = await _run_setup(item.definition.setup, audited, item.config)
            except BaseException:
                # Tear down already-started fibers before propagating so
                # the next plugin never sees a half-initialized ctx.
                raise
            disposer = _as_disposer(result)
            if disposer is not None:
                fiber.effect(disposer, label=f"plugin:{item.id}")
            # Actual interaction ⊆ declaration (P1).
            undeclared_provide = audited.provided - set(item.definition.provides)
            undeclared_require = audited.required - set(item.definition.requires)
            if undeclared_provide or undeclared_require:
                raise ProfileResolveError(
                    f"plugin {item.id}: undeclared interaction "
                    f"provide={sorted(undeclared_provide)} "
                    f"require={sorted(undeclared_require)}"
                )
            loaded.append(
                _EntryView(
                    id=item.id,
                    config=item.config,
                    inject=list(item.definition.requires),
                    provides=list(item.definition.provides),
                    extra={"$module": item.module},
                    disabled=False,
                )
            )
    except BaseException:
        await _dispose_context(ctx)
        raise

    ctx.__dict__["entries"] = loaded
    ctx.__dict__["resolved_profile"] = resolved
    return ctx


async def boot_entries(entries: list[dict[str, Any]]) -> Context:
    """Boot from already-expanded entry dicts (tests / programmatic trees).

    Validates Manifest id consistency and uses requires for ordering when
    modules expose ``@plugin`` metadata; falls back to list order for
    incomplete fixtures.
    """
    prepared = prepare_entries(entries)
    ctx = Context()
    fibers: list[Fiber] = []
    loaded: list[_EntryView] = []

    try:
        for entry, definition, config in prepared:
            fiber = ctx.registry.plugin(definition.setup, config=config)
            fibers.append(fiber)
            audited = AuditedPluginContext(_inner=ctx, _definition=definition)
            result = await _run_setup(definition.setup, audited, config)
            disposer = _as_disposer(result)
            if disposer is not None:
                fiber.effect(disposer, label=f"plugin:{definition.id}")
            loaded.append(
                _EntryView(
                    id=definition.id,
                    config=config,
                    inject=list(definition.requires),
                    provides=list(definition.provides),
                    extra={"$module": entry.get("$module")},
                    disabled=False,
                )
            )
    except BaseException:
        await _dispose_context(ctx)
        raise

    ctx.__dict__["entries"] = loaded
    return ctx


async def boot_profile(profile_path: Path | str) -> Context:
    """Compat façade: resolve then boot (ADR-0061)."""
    resolved = resolve_profile(profile_path)
    return await boot_resolved_profile(resolved)


# ── Helpers ─────────────────────────────────────────────────────────


class _EntryView:
    """Duck-typed stand-in for cordis Entry used by BootReport / inspect."""

    def __init__(
        self,
        *,
        id: str,
        config: Any,
        inject: list[str],
        provides: list[str],
        extra: dict[str, Any],
        disabled: bool,
    ) -> None:
        self.id = id
        self.config = config
        self.inject = inject
        self.provides = provides
        self.extra = extra
        self.disabled = disabled


async def _run_setup(setup_fn: Callable[..., Any], ctx: Any, config: Any) -> Any:
    """Invoke setup() and await if it returned a coroutine."""
    result = setup_fn(ctx, config)
    if hasattr(result, "__await__"):
        return await result
    return result


def _as_disposer(result: Any) -> Callable[[], Any] | None:
    """Wrap a setup() return value as a disposer callback, if applicable."""
    if result is None or not callable(result):
        return None
    disposer: Callable[[], Any] = result
    return disposer


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
