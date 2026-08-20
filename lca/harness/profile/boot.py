"""Boot a harness plugin tree from a profile YAML (ADR-0061).

Public API:
  - ``resolve_profile`` / ``boot_resolved_profile`` — two-phase model
  - ``boot_profile`` — compat façade (resolve then boot)
  - ``load_profile_entries`` / ``boot_entries`` — retained for tests that
    assemble entry dicts without a profile file; ``boot_entries`` still
    goes through Manifest validation when modules declare ``@plugin``.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cordis import Context

from lca.harness.plugin_api import AuditedPluginContext, definition_from_plugin
from lca.harness.profile.resolve import (
    ProfileResolveError,
    ResolvedProfile,
    dump_resolved,
    resolve_profile,
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
    """Execute phase: setup plugins in DAG order under audited PluginContext."""
    ctx = Context()
    started: list[tuple[str, Callable[[], Any] | None]] = []
    loaded_meta: list[Any] = []

    try:
        for item in resolved.plugins:
            if item.disabled:
                continue
            audited = AuditedPluginContext(_inner=ctx, _definition=item.definition)
            result = await _call_setup(item.definition.setup, audited, item.config)
            disposer = _as_disposer(result)
            if disposer is not None:
                ctx.effect(disposer, label=f"plugin:{item.id}")
            started.append((item.id, disposer))
            # Actual interaction ⊆ declaration (P1).
            undeclared_provide = audited.provided - set(item.definition.provides)
            undeclared_require = audited.required - set(item.definition.requires)
            if undeclared_provide or undeclared_require:
                raise ProfileResolveError(
                    f"plugin {item.id}: undeclared interaction "
                    f"provide={sorted(undeclared_provide)} require={sorted(undeclared_require)}"
                )
            loaded_meta.append(
                _EntryView(
                    id=item.id,
                    config=item.config,
                    inject=list(item.definition.requires),
                    provides=list(item.definition.provides),
                    extra={"$module": item.module},
                    disabled=False,
                )
            )
    except Exception:
        await _dispose_started(started)
        raise

    ctx.__dict__["entries"] = loaded_meta
    ctx.__dict__["resolved_profile"] = resolved
    return ctx


async def boot_entries(entries: list[dict[str, Any]]) -> Context:
    """Boot from already-expanded entry dicts (tests / programmatic trees).

    Validates Manifest id consistency and uses requires for ordering when
    modules expose ``@plugin`` metadata; falls back to list order for
    incomplete fixtures.
    """
    # Materialize a synthetic ResolvedProfile-like boot without re-reading YAML.
    prepared: list[tuple[dict[str, Any], Any, Any]] = []
    provide_owner: dict[str, str] = {}
    for index, entry in enumerate(entries):
        if entry.get("disabled") or (
            isinstance(entry.get("config"), dict) and entry["config"].get("disabled")
        ):
            continue
        module_path = entry.get("$module")
        if not module_path:
            raise ValueError(
                f"bundle entry {entry.get('id')!r} has no $module; bare-name resolution was removed"
            )
        module = importlib.import_module(str(module_path))
        setup_obj = getattr(module, "setup", None)
        if setup_obj is None:
            continue
        definition = definition_from_plugin(setup_obj, module=str(module_path))
        entry_id = str(entry.get("id") or definition.id)
        if definition.id and entry_id != definition.id:
            raise ValueError(f"entry id {entry_id!r} != module Manifest id {definition.id!r}")
        config = entry.get("config") or {}
        config_cls = definition.Config or getattr(setup_obj, "Config", None)
        if config_cls is not None and not isinstance(config, config_cls):
            config = config_cls.model_validate(config)
        for key in definition.provides:
            if key in provide_owner:
                raise ValueError(
                    f"duplicate providers for capability {key!r}: "
                    f"{provide_owner[key]} and {entry_id}"
                )
            provide_owner[key] = entry_id
        prepared.append(({"id": entry_id, "index": index, **entry}, definition, config))

    # Topo by requires among prepared entries; stable by index.
    ordered = _order_prepared(prepared)
    ctx = Context()
    started: list[tuple[str, Callable[[], Any] | None]] = []
    loaded: list[Any] = []
    try:
        for entry, definition, config in ordered:
            audited = AuditedPluginContext(_inner=ctx, _definition=definition)
            result = await _call_setup(definition.setup, audited, config)
            disposer = _as_disposer(result)
            if disposer is not None:
                ctx.effect(disposer, label=f"plugin:{definition.id}")
            started.append((definition.id, disposer))
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
    except Exception:
        await _dispose_started(started)
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


async def _call_setup(setup_fn: Callable[..., Any], ctx: Any, config: Any) -> Any:
    result = setup_fn(ctx, config)
    if hasattr(result, "__await__"):
        return await result
    return result


def _as_disposer(result: Any) -> Callable[[], Any] | None:
    if result is None or not callable(result):
        return None
    disposer: Callable[[], Any] = result
    return disposer


async def _dispose_started(
    started: list[tuple[str, Callable[[], Any] | None]],
) -> None:
    for _plugin_id, disposer in reversed(started):
        if disposer is None:
            continue
        try:
            result = disposer()
            if hasattr(result, "__await__"):
                await result
        except Exception as exc:
            _ = exc


def _order_prepared(
    prepared: list[tuple[dict[str, Any], Any, Any]],
) -> list[tuple[dict[str, Any], Any, Any]]:
    from collections import defaultdict, deque

    by_id = {definition.id: (entry, definition, config) for entry, definition, config in prepared}
    provide_owner = {
        key: definition.id for _, definition, _ in prepared for key in definition.provides
    }
    dependents: dict[str, set[str]] = defaultdict(set)
    reverse: dict[str, set[str]] = defaultdict(set)
    for _entry, definition, _config in prepared:
        for key in definition.requires:
            owner = provide_owner.get(key)
            if owner and owner != definition.id:
                dependents[owner].add(definition.id)
                reverse[definition.id].add(owner)
    indegree = {did: len(reverse[did]) for did in by_id}
    ready = deque(
        sorted(
            (did for did, deg in indegree.items() if deg == 0),
            key=lambda i: int(by_id[i][0].get("index", 0)),
        )
    )
    ordered: list[tuple[dict[str, Any], Any, Any]] = []
    while ready:
        nid = ready.popleft()
        ordered.append(by_id[nid])
        for child in sorted(dependents[nid], key=lambda i: int(by_id[i][0].get("index", 0))):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
        if len(ready) > 1:
            ready = deque(sorted(ready, key=lambda i: int(by_id[i][0].get("index", 0))))
    if len(ordered) != len(prepared):
        raise ValueError("cyclic plugin dependency in boot_entries")
    return ordered
