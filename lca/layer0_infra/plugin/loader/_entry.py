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

    config: dict[str, Any] = field(default_factory=dict)
    """Raw config dict from YAML (validated by plugin's Config class)."""

    disabled: bool = False
    """If True, loader skips this entry entirely."""

    source: str = ""
    """Which bundle/patch file this entry came from (for diagnostics)."""

    plugin_name: str = ""
    """Import path string; ProfileLoader resolves this to ``module``."""

    inject: tuple[str, ...] | dict[str, Any] | None = None
    """Override inject from YAML (if present, replaces module's inject)."""


@dataclass
class BootedTree:
    """Result of loading all entries. Provides dispose for cleanup."""

    host: Any  # PluginHost — avoid circular import at module level
    entries: list[PluginEntry]
    _disposers: list[tuple[str, Any]] = field(default_factory=list)

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
