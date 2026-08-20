"""Compat shim — convert LCA plugin pattern (manifest + apply) to cordis @plugin.

Each existing plugin module exports:
- `manifest` (PluginManifest dataclass)
- `name` (str)
- `provides` (tuple[str, ...])
- `apply(ctx, config)` (sync function)

This module imports each plugin module and exposes a `setup` async function
that delegates to the original `apply()`. Boot.py uses this so all 21 plugins
work without modification. The full rewriting to `@plugin decorator` async
setup happens in Chunk 2; this shim is the migration bridge.
"""
from __future__ import annotations

import importlib
from typing import Any

from cordis import Context

# Plugin module paths that follow the legacy pattern (manifest + apply)
# Order matters — must match bundle YAML order
_LEGACY_PLUGINS = [
    "lca.plugins.llm_service",
    "lca.plugins.llm_provider",
    "lca.plugins.tools_service",
    "lca.plugins.session_service",
    "lca.plugins.system_prompt",
    "lca.plugins.transport_service",
    "lca.plugins.skills_service",
    "lca.plugins.file_store_service",
    "lca.plugins.observability_service",
    "lca.plugins.sandbox_service",
    "lca.plugins.memory_service",
    "lca.plugins.search_service",
    "lca.plugins.state_store_service",
    "lca.plugins.loop_cognitive",
    "lca.plugins.loop_dsh_bridge",
    "lca.plugins.loop_replay",
    "lca.plugins.gateway_starlette",
    "lca.plugins.seam_definitions",
]


def _import_plugin(name: str) -> Any:
    """Import a plugin module. Returns the module."""
    return importlib.import_module(name)


def _resolve_plugin_attr(name: str, attr: str, default: Any = None) -> Any:
    """Get attr from plugin module, falling back to default."""
    try:
        mod = importlib.import_module(name)
        return getattr(mod, attr, default)
    except (ImportError, AttributeError):
        return default


# Helpers exported for boot.py
def legacy_plugin_setup(ctx: Context, plugin_name: str, config: Any) -> None:
    """Call the legacy plugin's `apply(ctx, config)` function.

    Used during the migration period where plugins still use the old
    manifest/apply pattern. Chunk 2 rewrites each plugin to use
    `@plugin` decorator + async setup function.
    """
    mod = _import_plugin(plugin_name)
    apply = getattr(mod, "apply", None)
    if apply is None:
        # No-op for plugins that don't define apply (e.g., seam_definitions)
        return
    apply(ctx, config)


def legacy_plugin_dependencies(plugin_name: str) -> list[str]:
    """Return the list of dependency keys (replaces old `inject` mechanism)."""
    mod = _import_plugin(plugin_name)
    inject = getattr(mod, "inject", None) or ()
    return list(inject)


def legacy_plugin_provides(plugin_name: str) -> tuple[str, ...]:
    """Return the keys this plugin provides."""
    mod = _import_plugin(plugin_name)
    provides = getattr(mod, "provides", None)
    if provides is not None:
        return tuple(provides) if isinstance(provides, (list, tuple)) else (provides,)
    # Fallback: try manifest
    manifest = getattr(mod, "manifest", None)
    if manifest is not None and hasattr(manifest, "provides"):
        return tuple(manifest.provides or ())
    return ()


def legacy_plugin_name(plugin_name: str) -> str:
    """Return the registered plugin name (used for diagnostics)."""
    mod = _import_plugin(plugin_name)
    return getattr(mod, "name", plugin_name)
