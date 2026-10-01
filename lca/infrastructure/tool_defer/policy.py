"""Defer policy: which namespaces stay eager, how the catalog reads."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True, slots=True)
class DeferPolicy:
    """Run-level switchboard for deferred tool loading."""

    enabled: bool = True
    """False restores legacy behavior: every tool schema, every turn."""

    eager_namespaces: frozenset[str] = frozenset({"tool_search"})
    """Namespaces whose full schemas inject every turn. ``tool_search``
    must stay eager — it is the loader itself (Muse L0)."""

    namespace_descriptions: Mapping[str, str] = field(default_factory=dict)
    """Human-written catalog lines, keyed by namespace. Honest one-liners
    only — a misleading line hides the capability from the model."""

    catalog_hint: str = 'call tool_search(namespace="...") to load full schemas'

    discovery_rule: str = (
        "Before concluding a capability is unavailable, check the deferred "
        "namespace catalog above — deferred namespaces load on demand via "
        "tool_search."
    )

    @classmethod
    def default(cls) -> DeferPolicy:
        """The production default: defer everything except the loader."""
        return cls()


__all__ = ["DeferPolicy"]
