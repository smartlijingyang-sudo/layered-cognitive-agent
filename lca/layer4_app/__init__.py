"""Layer 4 — Application / composition root."""

from lca.layer4_app.api import Agent, Team, TeamLead
from lca.layer4_app.spawn import spawn_agent, spawn_team

__all__ = ["Agent", "Team", "TeamLead", "spawn_agent", "spawn_team"]
