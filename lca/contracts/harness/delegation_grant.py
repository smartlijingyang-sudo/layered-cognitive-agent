"""Monotonic capability grants for delegated child Agents."""

from __future__ import annotations

from lca.contracts.protocols.act.command_envelope import CapabilityGrant


def derive_child_grant(parent: CapabilityGrant, requested: CapabilityGrant) -> CapabilityGrant:
    """Derive a child grant only when capability, scope and effect are bounded."""

    if requested.capability != parent.capability:
        raise PermissionError("child capability exceeds parent grant")
    if requested.scope != parent.scope:
        raise PermissionError("child scope exceeds parent grant")
    if requested.effect_class != parent.effect_class:
        raise PermissionError("child effect class exceeds parent grant")
    return requested


__all__ = ["derive_child_grant"]
