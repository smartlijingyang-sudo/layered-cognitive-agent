"""PluginManifest — harness-level plugin descriptor.

Extends the legacy ``PluginSpec`` with seam unification fields,
scoped lifecycle, and typed plugin kinds. This is the single
source of truth for what a plugin *is* in the harness runtime.

Spec reference: §2.2.1 of ``docs/specs/harness-spine-spec.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal


class ScopeKind(Enum):
    """Scope hierarchy for plugin visibility and lifecycle."""

    DEPLOYMENT = "deployment"
    PROFILE = "profile"
    TEAM = "team"
    AGENT = "agent"
    SESSION = "session"


class PluginKind(Enum):
    """What role a plugin plays in the system."""

    SERVICE = "service"
    """Provides a core service (sessions, agents, tools)."""

    DEFINITION = "definition"
    """Declares an extension point (was Seam Definition) — declares a seam key and contract."""

    PROVIDER = "provider"
    """Implements an extension point (was Seam Provider)."""

    CONSUMER = "consumer"
    """Consumes a service or extension point (was Seam Consumer)."""

    BUNDLE = "bundle"
    """Pure composition, no logic of its own."""

    POLICY = "policy"
    """Governance policy (sandbox, approval, budget)."""


class ProviderMode(Enum):
    """Single-active vs multi-provider registry."""

    SINGLE = "single"
    """One active provider per scope (e.g. agent_loop, session persistence)."""

    REGISTRY = "registry"
    """Named registry, multiple providers coexist (e.g. llm, subagent, skills)."""


@dataclass(frozen=True)
class ExtensionPoint:
    """Declares an extension point exposed by a DEFINITION plugin.

    Corresponds to DSH waterfall/serial event names and LCA Seam Definitions.

    Semantics:
    - Other plugins can register middleware against this extension point.
    - Loader reconcile validates: DEFINITION must have at least one PROVIDER
      (optional seams may have zero) and ideally at least one CONSUMER.
    - ``dispatch_mode`` controls middleware execution order:
      - ``waterfall``: each middleware's output feeds the next.
      - ``serial``: all middleware receive the same input, results collected.
      - ``around``: onion model — outer wraps inner.
    """

    seam_key: str
    dispatch_mode: Literal["waterfall", "serial", "around"] = "waterfall"
    description: str = ""


@dataclass(frozen=True)
class CapabilityGrant:
    """Permission a plugin requires to operate."""

    capability: str
    """E.g. ``"tool.execute"``, ``"session.append"``, ``"agent.create"``."""

    scope: ScopeKind = ScopeKind.AGENT


@dataclass(frozen=True)
class PluginManifest:
    """Harness-level plugin descriptor.

    Fully declarative: everything the Loader needs to know about a plugin
    is captured here. Legacy ``PluginSpec`` modules are adapted via
    ``compat.manifest_from_spec()``.
    """

    id: str
    """Unique plugin identifier, e.g. ``"lca.loop.cognitive"``."""

    version: str
    """SemVer version string."""

    api_version: str
    """Harness API version this plugin targets, e.g. ``"lca-harness/1"``."""

    kind: PluginKind
    """What role this plugin plays."""

    requires: tuple[str, ...] = ()
    """Required service keys — must be available before this plugin activates."""

    optional_requires: tuple[str, ...] = ()
    """Optional service keys — used if available, not a hard dependency."""

    provides: tuple[str, ...] = ()
    """Service keys this plugin provides."""

    provider_mode: ProviderMode = ProviderMode.SINGLE
    """Whether this plugin is single-active or registry-style."""

    scopes: tuple[ScopeKind, ...] = (ScopeKind.PROFILE,)
    """Scope levels at which this plugin is active."""

    permissions: tuple[CapabilityGrant, ...] = ()
    """Permissions this plugin requires."""

    config_model: type | None = None
    """Pydantic model for config validation. None = no config."""

    reload: Literal["never", "restart_scope", "hot_safe"] = "restart_scope"
    """Hot-replacement safety level."""

    # ── Seam unification fields (§3.7) ──

    seam_key: str | None = None
    """Associated seam key. Required for DEFINITION/PROVIDER/CONSUMER kinds."""

    extension_points: tuple[ExtensionPoint, ...] = ()
    """Extension points declared by this plugin. Only used by DEFINITION kind."""

    middleware: tuple[str, ...] = ()
    """Extension point seam_keys this plugin registers middleware against.
    Used by PROVIDER/CONSUMER/POLICY kinds."""
