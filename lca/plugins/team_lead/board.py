"""BoardLead plugin — Tier-3 (LCA team-lead mandate `board`).

Note: BoardLead / ConsultLead are TeamStrategy implementations, not
standalone plugin types. They live in lca/layer3_agent/orchestration_strategies/.
This plugin registers the strategy registry at the team_lead_factory key
so the composition root can resolve them.
"""

from __future__ import annotations

from typing import Any

from lca.contracts.protocols import TeamStrategy
from lca.plugins._cordis_adapter import plugin


@plugin(
    name="lca-team-lead-board",
    provides=["team_lead_factory"],
    implements=[TeamStrategy],
    layer="behavior",
    side_effects="none",
    policy_class="control",
    description="Register the team strategy registry at team_lead_factory.",
    test_suite="tests/test_plugin_alignment.py",
)
async def setup(ctx: Any, config: Any) -> None:
    """Register the team strategy registry at team_lead_factory."""
    from lca.layer3_agent.orchestration_registry import TeamStrategyRegistry

    factory = TeamStrategyRegistry()
    ctx.provide("team_lead_factory", factory)
