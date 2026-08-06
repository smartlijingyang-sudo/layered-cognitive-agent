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
from lca.layer4_app.api import Agent, Team, TeamLead

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
