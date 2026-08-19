"""PluginMeta — typed contract for v3 plugin metadata (PR12 / D8).

The v3 spec asserts that plugin metadata lives in a single TypedDict
schema (no parallel ``PrimitiveManifest`` schema).  The Contracts
TypedDict is the authoritative type; the inspect CLI (PR12) derives
the capability graph from ``@plugin(..., meta=...)`` and the bundle
YAML.

The TypedDict is intentionally permissive — keys are optional so
existing plugins can adopt it incrementally.  Composers do NOT refuse
unknown plugins until the meta coverage gate is lifted (per spec
§13.3.1 C5).
"""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

# Plugin layer taxonomy (spec §3.5).
PluginLayer = Literal[
    "service",  # Tier-1: @plugin(name="lca-*") — service definition
    "provider",  # Tier-2: single plugin + multiple providers
    "behavior",  # Tier-3: aspect / middleware / brain variant
    "guard",  # Tier-3: DecisionGate / guard
    "sensor",  # Tier-3: sensor named factory
]


class PluginMeta(TypedDict, total=False):
    """TypedDict for v3 plugin metadata.

    The fields are all optional so plugins can adopt the schema
    incrementally.  The ``layer`` and ``name`` fields are the
    minimum useful subset — the inspect CLI uses them to render the
    capability graph.
    """

    layer: PluginLayer
    """Which Tier the plugin belongs to (service / provider / behavior / guard / sensor)."""

    name: str
    """The canonical plugin name (matches ``@plugin(name=...)``)."""

    provides: NotRequired[list[str]]
    """The capability keys this plugin publishes (``ctx.provide(...)``)."""

    requires: NotRequired[list[str]]
    """Capability keys this plugin depends on."""

    seam_keys: NotRequired[list[str]]
    """For middleware / guard plugins: the cognitive seam keys they bind to."""

    description: NotRequired[str]
    """Free-form description for the inspect CLI."""

    version: NotRequired[str]
    """Plugin version (for the inspect graph)."""


# Convenience constants for the inspect CLI / tests.
NAME_FIELD = "name"
LAYER_FIELD = "layer"
PROVIDES_FIELD = "provides"
REQUIRES_FIELD = "requires"
SEAM_KEYS_FIELD = "seam_keys"
DESCRIPTION_FIELD = "description"
VERSION_FIELD = "version"
