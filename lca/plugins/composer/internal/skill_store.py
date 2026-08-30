"""Resolve the active skill-store provider for composition concerns."""

from __future__ import annotations

from typing import Any

from lca.contracts.mechanisms.capability import (
    MissingCapabilityError,
    provider_current,
    require_capability,
)


def active_skill_store(scope: object) -> Any:
    """Return the active store behind the declared ``skills`` capability."""

    store = provider_current(require_capability(scope, "skills"))
    if store is None:
        raise MissingCapabilityError("skills")
    return store


__all__ = ["active_skill_store"]
