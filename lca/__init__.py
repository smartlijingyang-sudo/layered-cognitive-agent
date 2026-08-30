"""LCA Framework — Layered Cognitive Agent.

The root package exposes value types from ``contracts``.  Its optional
``Agent`` / ``Team`` facade is resolved only for callers that explicitly ask
for those composition-root symbols; importing a lower-layer submodule must
not create a static dependency on ``layer4_app``.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from lca.contracts.models.team.team_coordination import (
    Debate,
    FanOut,
    Graph,
    LeadMandate,
    PeerRelay,
    PeerSwarm,
    Pipeline,
)
from lca.contracts.protocols.spec import AgentSpec, Governance, LeadSpec, TeamSpec

__all__ = [
    "Agent",
    "AgentSpec",
    "Debate",
    "FanOut",
    "Governance",
    "Graph",
    "LeadMandate",
    "LeadSpec",
    "PeerRelay",
    "PeerSwarm",
    "Pipeline",
    "Team",
    "TeamLead",
    "TeamSpec",
]

_LAZY_COMPOSITION_SYMBOLS = frozenset({"Agent", "Team", "TeamLead"})


def __getattr__(name: str) -> Any:
    """Resolve composition-root symbols only for explicit public-facade access.

    The import target intentionally remains behind this adapter.  Layered code
    imports concrete submodules directly, while external callers can retain the
    concise ``from lca import Agent`` form without making package initialisation
    a reverse dependency edge.
    """

    if name not in _LAZY_COMPOSITION_SYMBOLS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    api = import_module("lca.application.api")
    value = getattr(api, name)
    globals()[name] = value
    return value
