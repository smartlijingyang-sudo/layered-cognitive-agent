"""Plugin config base class — post-cordis migration.

`PluginConfig` Pydantic model with `extra="forbid"` is held here as a
shared base for plugin-specific config models. cordis uses Standard Schema
(Pydantic v2 compatible), so any subclass with `model_config = {"extra": "forbid"}`
is consumable.

The `Plugin` Protocol (name/inject/provides/apply/Config) is deleted —
cordis's `@plugin` decorator replaces it.
"""
from __future__ import annotations

from pydantic import BaseModel


class PluginConfig(BaseModel):
    """Plugin config base class: default empty, unknown fields rejected."""

    model_config = {"extra": "forbid"}
