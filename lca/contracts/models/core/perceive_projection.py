"""Typed perceive projection on AgentState (ADR-0191 R3 / C4)."""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.models.core.perception import ContextManifest


@dataclass(frozen=True, slots=True)
class PerceiveProjection:
    """Reducer-owned view of the latest ContextManifest for one step."""

    manifest: ContextManifest
    digest: str
    step: int


def current_manifest_from_state(state: object) -> ContextManifest | None:
    """Return the reducer projection manifest, or ``None`` when unset."""
    projection = getattr(state, "perceive", None)
    if projection is None:
        return None
    manifest = getattr(projection, "manifest", None)
    if isinstance(manifest, ContextManifest):
        return manifest
    return None


__all__ = ["PerceiveProjection", "current_manifest_from_state"]
