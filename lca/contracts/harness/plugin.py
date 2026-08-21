"""Harness plugin shape — post-cordis migration.

PluginManifest / ExtensionPoint / CapabilityGrant / ScopeKind / PluginKind /
ProviderMode are kept as DEPRECATED compatibility aliases for the migration
period. cordis's @plugin + Standard Schema cover the same ground; once all
21 plugins are rewritten to @plugin form (Chunk 2), these aliases will be
deleted.

PluginContext Protocol is the stable type alias for migration-period
compatibility. Uses ONLY cordis's public surface (provide / inject / on /
once / scope / dispose).
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

# ── PluginContext Protocol (kept; cordis surface only) ───────────────


class PluginContext(Protocol):
    """Stable name for migration-period type alias.

    Resolves to cordis.Context at runtime. After Chunk 5 migration,
    callers should use cordis.Context directly.
    """

    def provide(self, key: str, value: Any) -> None: ...
    def inject(self, key: str) -> Any: ...
    def on(self, event: str, callback: Any) -> None: ...
    def once(self, event: str, callback: Any) -> None: ...


# ── Deprecated aliases (kept for migration period; remove in Chunk 2) ──


class ScopeKind(Enum):
    """DEPRECATED: ScopeKind is gone. cordis.Context.scope(label) replaces.

    Kept as deprecated alias for migration period."""

    DEPLOYMENT = "deployment"
    PROFILE = "profile"
    TEAM = "team"
    AGENT = "agent"
    SESSION = "session"


def _scope_kind_deprecation_warning() -> None:
    warnings.warn(
        "ScopeKind is deprecated; cordis.Context.scope(label) replaces",
        DeprecationWarning,
        stacklevel=3,
    )


class PluginKind(Enum):
    """DEPRECATED: PluginKind is gone. cordis @plugin decorator replaces."""

    SERVICE = "service"
    DEFINITION = "definition"
    PROVIDER = "provider"
    CONSUMER = "consumer"
    BUNDLE = "bundle"
    POLICY = "policy"


class ProviderMode(Enum):
    """DEPRECATED: ProviderMode is gone. cordis uses active= on register."""

    SINGLE = "single"
    REGISTRY = "registry"


@dataclass(frozen=True)
class ExtensionPoint:
    """DEPRECATED: ExtensionPoint is gone. cordis events replace."""

    seam_key: str
    dispatch_mode: str = "waterfall"
    description: str = ""


@dataclass(frozen=True)
class CapabilityGrant:
    """DEPRECATED: CapabilityGrant is gone. cordis pydantic config replaces."""

    capability: str
    scope: str = "agent"


@dataclass(frozen=True)
class PluginManifest:
    """DEPRECATED: PluginManifest is gone. cordis @plugin decorator replaces."""

    id: str = ""
    version: str = "1.0.0"
    api_version: str = "lca-harness/1"
    kind: PluginKind = PluginKind.SERVICE
    provides: tuple[str, ...] = field(default_factory=tuple)
    requires: tuple[str, ...] = field(default_factory=tuple)
    inject: tuple[str, ...] = field(default_factory=tuple)
    seam_key: str = ""
    dispatch_mode: str = "waterfall"
    middleware: tuple[str, ...] = field(default_factory=tuple)
    optional_requires: tuple[str, ...] = field(default_factory=tuple)
