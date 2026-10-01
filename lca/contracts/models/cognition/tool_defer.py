"""Deferred tool-namespace contracts (Muse-style defer alignment).

A *namespace* groups the tools one factory registered (the ``ToolsService``
factory key, e.g. ``"browser"``).  Per turn the runtime injects only a
one-line catalog entry for each deferred namespace; the agent loads full
parameter schemas on demand via the ``tool_search`` tool.  Source design:
ADR-0255 §3 (Muse production runtime reference).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DeferMode(str, Enum):
    """Per-namespace injection mode."""

    EAGER = "eager"
    """Full schemas injected every turn (Muse L0 — always affordable)."""

    DEFERRED = "deferred"
    """Catalog line only; full schemas load via ``tool_search`` (Muse L1)."""


@dataclass(frozen=True, slots=True)
class ToolNamespace:
    """Contracts-layer declaration of one defer namespace.

    Pure data — the infrastructure layer derives instances per turn from
    the forked ``ToolsService``; no behavior lives here.
    """

    name: str
    """Factory key, e.g. ``"browser"``. Stable across the turns of a run."""

    description: str
    """One honest catalog line. Shown to the model verbatim."""

    mode: DeferMode = DeferMode.DEFERRED

    tool_names: tuple[str, ...] = ()
    """Tool names currently visible in this namespace (per-turn view)."""


__all__ = ["DeferMode", "ToolNamespace"]
