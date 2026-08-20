"""Compat shim — re-exports :func:`lca.harness.plugin_api.plugin` (ADR-0061).

Existing plugins may keep importing ``from lca.plugins._cordis_adapter import plugin``.
New code should prefer ``lca.harness.plugin_api``. Legacy kwargs
(``name``, ``side_effects``, ``policy_class``, taxonomy ``layer``) still work;
canonical fields are ``id``, ``kind``, ``effects``, ``layer`` in ``L0``–``L4``.
"""

from __future__ import annotations

from lca.harness.plugin_api import (
    EffectClass,
    PluginContext,
    PluginDefinition,
    PluginKind,
    UndeclaredInteractionError,
    definition_from_plugin,
    plugin,
)

__all__ = [
    "EffectClass",
    "PluginContext",
    "PluginDefinition",
    "PluginKind",
    "UndeclaredInteractionError",
    "definition_from_plugin",
    "plugin",
]
