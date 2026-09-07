"""ExternalPluginKind — runtime isolation tier (ADR-0199 §3.4 / P5-02).

Per ADR-0199 §3.4 + §10 Phase 5: plugins with ``source`` in
``{"project", "pip"}`` default to ``untrusted``. The runtime cannot
silently admit them — they need a runtime isolation tier
(``inprocess`` / ``mcp`` / ``sandbox`` / ``worker``).

This module is the closed-set enum that drives runtime isolation,
not the plugin's contract. Plugins may declare a preferred kind in
their manifest; the operator decides the actual kind via Profile
provenance (per the rubric in
``docs/specs/external-plugin-trust-rubric.md``).

Per I-HPC-11: default for ``project`` / ``pip`` source is ``mcp``
unless explicitly overridden.
"""

from __future__ import annotations

from typing import Final, Literal

# Closed set of runtime isolation tiers.
# Adding a new kind requires an ADR.
ExternalPluginKind = Literal[
    "inprocess",  # shared cordis fiber (trusted core)
    "mcp",  # Model Context Protocol (separate process)
    "sandbox",  # OS-level sandbox (Firecracker / gVisor)
    "worker",  # Separate Python worker (subprocess)
]


# Per ADR-0199 §3.4: untrusted defaults to `mcp`; trusted defaults to
# `inprocess`.
DEFAULT_EXTERNAL_KIND_BY_TRUST: Final[dict[str, ExternalPluginKind]] = {
    "core": "inprocess",
    "trusted": "inprocess",
    "untrusted": "mcp",
}


def default_external_kind(trust: str) -> ExternalPluginKind:
    """Return the default ExternalPluginKind for a given trust level.

    Per ADR-0199 §3.4: bundled (core) + user (trusted) → inprocess;
    project / pip (untrusted) → mcp.

    Unknown trust levels raise ValueError (no implicit fallback).
    """
    if trust not in DEFAULT_EXTERNAL_KIND_BY_TRUST:
        raise ValueError(
            f"unknown trust level {trust!r}; expected one of: "
            f"{sorted(DEFAULT_EXTERNAL_KIND_BY_TRUST)}"
        )
    return DEFAULT_EXTERNAL_KIND_BY_TRUST[trust]


def is_high_isolation_kind(kind: ExternalPluginKind) -> bool:
    """Return True if the kind provides OS-level or process-level isolation."""
    return kind in ("mcp", "sandbox", "worker")


def is_sandbox_kind(kind: ExternalPluginKind) -> bool:
    """Return True if the kind uses OS-level sandbox (vs. process isolation)."""
    return kind == "sandbox"


__all__ = (
    "DEFAULT_EXTERNAL_KIND_BY_TRUST",
    "ExternalPluginKind",
    "default_external_kind",
    "is_high_isolation_kind",
    "is_sandbox_kind",
)
