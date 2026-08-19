"""BoardLead plugin — Tier-3 (LCA team-lead mandate `board`)."""
from __future__ import annotations

from cordis import plugin


@plugin(name="lca-team-lead-board")
async def setup(ctx, config) -> None:
    """Register the BoardLead strategy as 'board' in the team-lead factory."""
    from lca.layer3_agent.orchestration_strategies.lead import (
        BoardLead,
    )
    from lca.layer3_agent.orchestration_registry import OrchestrationFactory

    factory = OrchestrationFactory()
    factory.register_lead("board", BoardLead)
    ctx.provide("team_lead_factory", factory)
