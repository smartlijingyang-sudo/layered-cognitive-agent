"""LCA Framework — Layered Cognitive Agent.

Public API::

    from lca import Agent, Team, TeamLead, LeadMandate, Pipeline, FanOut, ...
"""

from lca.contracts.team_coordination import (
    Debate,
    FanOut,
    Graph,
    LeadMandate,
    PeerRelay,
    PeerSwarm,
    Pipeline,
)
from lca.layer4_app.api import Agent, Team, TeamLead

__all__ = [
    "Agent",
    "Debate",
    "FanOut",
    "Graph",
    "LeadMandate",
    "PeerRelay",
    "PeerSwarm",
    "Pipeline",
    "Team",
    "TeamLead",
]
