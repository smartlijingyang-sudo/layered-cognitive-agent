"""BoardLead plugin — Tier-3 (LCA team-lead mandate `board`).

Note: BoardLead / ConsultLead are TeamStrategy implementations, not
standalone plugin types. They live in lca/layer3_agent/orchestration_strategies/.
This plugin registers the strategy registry at the team_lead_factory key
so the composition root can resolve them.
"""
from __future__ import annotations

from typing import Any

from cordis import Context, plugin


@plugin(name="lca-team-lead-board")
async def setup(ctx: Context, config: Any) -> None:
    """Register the team strategy registry at team_lead_factory."""
    from lca.layer3_agent.orchestration_registry import TeamStrategyRegistry

    factory = TeamStrategyRegistry()
    ctx.provide("team_lead_factory", factory)
