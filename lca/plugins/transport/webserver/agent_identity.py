"""Neutral home for the run principal identity type.

``AgentRef`` is needed on both sides of the ADR-0195 P-L3 boundary:
``carrier/`` (to rebuild a run's identity when resuming a run) and
``read/`` (where it was historically defined). Defining it here — a
sibling of both, with zero lca imports — lets carrier import it without
tripping the P-L3 "no read/fold/deriver import" pin.
``read/runs/identity.py`` re-exports it so existing importers keep working.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_AGENT_ID = "solo"


@dataclass(frozen=True)
class AgentRef:
    """Stable principal: id is the isolation key, name is the display role."""

    agent_id: str
    name: str


__all__ = [
    "DEFAULT_AGENT_ID",
    "AgentRef",
]
