"""Layer 4 — Application / composition root."""

from lca.application.api.api import Agent, Team, TeamLead
from lca.application.api.spawn import spawn_agent, spawn_team

__all__ = ["Agent", "Team", "TeamLead", "spawn_agent", "spawn_team"]
