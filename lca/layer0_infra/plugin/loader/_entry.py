"""PluginEntry — one row in a profile YAML.

Mirrors DSH ``loader/src/config/entry.ts``. An entry is a declarative
description: id + module path + config + inject + disabled. The Loader
resolves ``module`` by importing the ``name`` path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PluginEntry:
    """One profile row (before module resolution)."""

    id: str
    """Unique entry id in the plugin tree."""

    module: Any = None
    """Resolved plugin module (None before import)."""

    config: dict[str, Any] | list[PluginEntry] = field(default_factory=dict)
    """Raw config dict from YAML (validated by plugin's Config class)."""

    disabled: bool = False
    """If True, loader skips this entry entirely."""

    source: str = ""
    """Which bundle/patch file this entry came from (for diagnostics)."""

    plugin_name: str = ""
    """Import path string; ProfileLoader resolves this to ``module``."""

    inject: tuple[str, ...] | dict[str, Any] | None = None
    """Override inject from YAML (if present, replaces module's inject)."""

    group: bool = False
    """Group entry: config holds a list of child PluginEntry rows (Cordis ``EntryGroup``)."""

    isolate: dict[str, Any] | None = None
    """Service keys this group isolates from the parent realm (Cordis ``isolate``)."""

    _original_module: Any = None
    """Module object before Loader replaces ``module`` with PluginSpec."""


def _copy_entry(entry: PluginEntry, **overrides: Any) -> PluginEntry:
    """Build a detached copy of *entry* (patch semantics never mutate input)."""
    import copy

    return PluginEntry(
        id=entry.id,
        module=entry.module,
        config=copy.deepcopy(entry.config),
        disabled=entry.disabled,
        source=entry.source,
        plugin_name=entry.plugin_name,
        inject=entry.inject,
        group=entry.group,
        isolate=copy.deepcopy(entry.isolate) if entry.isolate else None,
        _original_module=entry._original_module,
        **overrides,
    )


@dataclass
class BootedTree:
    """Result of loading all entries. Provides dispose for cleanup."""

    host: Any  # PluginHost — avoid circular import at module level
    entries: list[PluginEntry]
    _disposers: list[tuple[str, Any]] = field(default_factory=list)
    _profile_path: str | None = None
    _loader: Any = None
    _writable: bool = False

    def dispose(self) -> None:
        """LIFO dispose all loaded plugins."""

        errors: list[tuple[str, BaseException]] = []
        for plugin_id, disposer in reversed(self._disposers):
            try:
                disposer()
            except Exception as exc:
                errors.append((plugin_id, exc))
        self._disposers.clear()
        if errors:
            import structlog

            structlog.get_logger("lca.plugin").warning(
                "loader_dispose_errors",
                count=len(errors),
                plugins=[pid for pid, _ in errors],
            )

    # ── Runtime mutation API (Cordis EntryTree mirror) ─────

    def resolve(self, entry_id: str) -> PluginEntry | None:
        """Resolve an entry by id, including nested ``parent:child`` ids."""
        if ":" in entry_id:
            parent_id, _, child_id = entry_id.partition(":")
            parent = self._find(parent_id)
            if parent is None or not parent.group or not isinstance(parent.config, list):
                return None
            for child in parent.config:
                if child.id == child_id:
                    return child
            return None
        return self._find(entry_id)

    def _find(self, entry_id: str) -> PluginEntry | None:
        for entry in self.entries:
            if entry.id == entry_id:
                return entry
            if entry.group and isinstance(entry.config, list):
                for child in entry.config:
                    if child.id == entry_id:
                        return child
        return None

    def _all_handles(self) -> list[Any]:
        handles: list[Any] = []
        for entry in self.entries:
            handle = self.host.handles.get(entry.id)
            if handle is not None:
                handles.append(handle)
            if entry.group and isinstance(entry.config, list):
                for child in entry.config:
                    handle = self.host.handles.get(child.id)
                    if handle is not None:
                        handles.append(handle)
        return handles

    async def create(self, options: PluginEntry, parent: str | None = None) -> str:
        """Runtime-add an entry. Returns the new entry id."""
        if self._loader is None:
            raise RuntimeError("BootedTree has no loader attached; runtime mutation disabled")
        new_entry = _copy_entry(options)
        if parent is not None:
            target = self._find(parent)
            if target is None or not target.group or not isinstance(target.config, list):
                raise KeyError(f"parent {parent!r} is not a group entry")
            target.config.append(new_entry)
        await self._loader.add_entry(self, new_entry)
        self._write()
        return new_entry.id

    async def remove(self, entry_id: str) -> None:
        """Runtime-remove an entry, deactivating it and cascading."""
        if self._loader is None:
            raise RuntimeError("BootedTree has no loader attached; runtime mutation disabled")
        await self._loader.remove_entry(self, entry_id)
        self._write()

    async def update_entry(
        self,
        entry_id: str,
        *,
        config: Any = None,
        inject: Any = None,
        name: str | None = None,
        disabled: bool | None = None,
    ) -> None:
        """Update an entry with three-state diff (config restart vs full replace)."""
        entry = self.resolve(entry_id)
        if entry is None:
            raise KeyError(f"entry {entry_id!r} not found")
        handle = self.host.handles.get(entry.id)

        if disabled is not None:
            entry.disabled = disabled
            if handle is not None:
                handle.desired = not disabled
                from lca.layer0_infra.plugin.kernel import deactivate, reconcile

                if disabled:
                    await deactivate(self.host, handle, permanent=True)
                else:
                    await reconcile(self.host)

        if name is not None and name != entry.plugin_name:
            # Full replacement path: dispose + re-import + restart
            old = entry.plugin_name
            entry.plugin_name = name
            if handle is not None:
                from lca.layer0_infra.plugin.kernel import deactivate

                await deactivate(self.host, handle, permanent=True)
                self.host.unregister_handle(entry.id)
            entry.module = None
            try:
                await self._reload_entry(entry)
            except BaseException:
                entry.plugin_name = old
                await self._reload_entry(entry)
                raise

        if config is not None:
            entry.config = config
            if handle is not None and not entry.disabled:
                from lca.layer0_infra.plugin.kernel import update_config

                await update_config(self.host, entry.id, config)

        if inject is not None:
            entry.inject = inject

        self._write()

    async def _reload_entry(self, entry: PluginEntry) -> None:
        if self._loader is None:
            return
        if entry.module is None and entry.plugin_name:
            import importlib

            entry.module = importlib.import_module(entry.plugin_name)
        await self._loader.reload(self)

    def write(self) -> None:
        """Serialize the current entry list back to the profile file."""
        self._write()

    def _write(self) -> None:
        if not self._writable or not self._profile_path:
            return
        from pathlib import Path

        import yaml

        payload = {"bundles": _bundles_of(self.entries), "patch": _patches_of(self.entries)}
        path = Path(self._profile_path)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(yaml.safe_dump(payload, sort_keys=False))
        tmp.rename(path)

    async def refresh(self) -> None:
        """Re-read the profile file and transactionally update entries."""
        if self._loader is None or not self._profile_path:
            return
        from pathlib import Path

        fresh = await self._loader.load_profile(Path(self._profile_path))
        await self._loader.reload(self, fresh)


def _bundles_of(entries: list[PluginEntry]) -> list[str]:
    sources: list[str] = []
    for e in entries:
        if e.source and e.source not in sources and not e.source.startswith("patch"):
            sources.append(e.source)
    return sources


def _patches_of(entries: list[PluginEntry]) -> list[dict[str, Any]]:
    """Emit patch rows for every entry (id-based replacement, whole config)."""
    rows: list[dict[str, Any]] = []
    for e in entries:
        row: dict[str, Any] = {"id": e.id}
        if e.disabled:
            row["disabled"] = True
        if e.config:
            row["config"] = e.config
        rows.append(row)
    return rows
