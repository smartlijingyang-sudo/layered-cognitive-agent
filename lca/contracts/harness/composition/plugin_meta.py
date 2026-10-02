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

The schema (per spec §13.3.1):
- ``implements``: Protocol names this plugin implements
- ``emitted_events``: Journal event classes emitted by this plugin
- ``consumed_events``: Journal event classes this plugin reads
- ``context_fields``: Manifest item keys this plugin produces
- ``capabilities``: capability grant keys required
- ``side_effects``: ``none | tools | memory | world``
- ``policy_class``: ``observe | control | execute``
- ``test_suite``: pytest node id prefix for this plugin
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

# Side-effect taxonomy (PR12 / spec §13.3.1).
SideEffect = Literal[
    "none",
    "tools",
    "memory",
    "world",
]

# Policy classification (PR12 / spec §13.3.1).
PolicyClass = Literal[
    "observe",
    "control",
    "execute",
]


class PluginMeta(TypedDict, total=False):
    """TypedDict for v3 plugin metadata.

    Fields are all optional so plugins can adopt the schema
    incrementally.  ``name`` + ``layer`` + ``implements`` is the
    minimum useful subset — the inspect CLI uses them to render the
    capability graph.
    """

    # ── Identity ──
    layer: PluginLayer
    name: str
    version: str
    description: str

    # ── Capability graph (spec §13.3.1) ──
    implements: list[str]
    """Protocol names this plugin implements (``Sensor``, ``Brain``, etc.)."""
    provides: NotRequired[list[str]]
    """Capability keys published via ``ctx.provide(...)``."""
    requires: NotRequired[list[str]]
    """Capability keys this plugin depends on."""

    # ── Event surface (spec §13.3.1) ──
    emitted_events: list[str]
    """Journal event classes emitted by this plugin."""
    consumed_events: list[str]
    """Journal event classes this plugin reads."""

    # ── Context surface (spec §13.3.1) ──
    context_fields: list[str]
    """Manifest item keys this plugin produces (``clock``, ``workspace_artifacts``...)."""

    # ── Security & policy ──
    capabilities: list[str]
    """Capability grant keys this plugin requires."""
    side_effects: SideEffect
    policy_class: PolicyClass

    # ── Wiring ──
    seam_keys: NotRequired[list[str]]
    """For middleware / guard plugins: cognitive seam keys bound to."""
    test_suite: str
    """Pytest node id prefix for this plugin (``tests/test_*.py::...``)."""


# Convenience constants for the inspect CLI / tests.
NAME_FIELD = "name"
LAYER_FIELD = "layer"
PROVIDES_FIELD = "provides"
REQUIRES_FIELD = "requires"
SEAM_KEYS_FIELD = "seam_keys"
DESCRIPTION_FIELD = "description"
VERSION_FIELD = "version"
IMPLEMENTS_FIELD = "implements"
EMITTED_EVENTS_FIELD = "emitted_events"
CONSUMED_EVENTS_FIELD = "consumed_events"
CONTEXT_FIELDS_FIELD = "context_fields"
CAPABILITIES_FIELD = "capabilities"
SIDE_EFFECTS_FIELD = "side_effects"
POLICY_CLASS_FIELD = "policy_class"
TEST_SUITE_FIELD = "test_suite"
