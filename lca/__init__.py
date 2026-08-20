"""LCA Framework — Layered Cognitive Agent.

Public API::

    from lca import Agent, Team, TeamLead, LeadMandate, Pipeline, FanOut, ...
"""

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

_LAZY_LAYER4 = frozenset({"Agent", "Team", "TeamLead"})


def __getattr__(name: str) -> object:
    """Defer layer4 imports so ``lca.layer0_infra.*`` works in slim runtimes (DSH daemon)."""
    if name not in _LAZY_LAYER4:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from lca.layer4_app.api import Agent, Team, TeamLead

    mapping = {"Agent": Agent, "Team": Team, "TeamLead": TeamLead}
    value = mapping[name]
    globals()[name] = value
    return value
