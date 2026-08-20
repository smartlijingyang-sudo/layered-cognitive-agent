"""Lead strategy factory — registers into team_strategies."""

from __future__ import annotations

from typing import Any

from lca.contracts.capabilities import STRATEGIES
from lca.contracts.models.team.team_coordination import STRATEGY_KEY_LEAD, LeadMandate
from lca.contracts.protocols import TeamAssembly
from lca.contracts.protocols.spec import LeadSpec
from lca.harness.plugin_api import PluginKind, plugin

_DUTY_MANDATES: frozenset[LeadMandate] = frozenset({LeadMandate.CONSULT, LeadMandate.BOARD})


def build_lead_strategy(assembly: TeamAssembly) -> Any:
    from lca.layer1_cognitive.member_status import InMemoryMemberStatus
    from lca.layer3_agent.orchestration_strategies import LeadStrategy

    governance = assembly.governance
    if not isinstance(governance, LeadSpec) or assembly.lead is None:
        raise TypeError(f"strategy {STRATEGY_KEY_LEAD!r} requires LeadSpec governance")
    members = assembly.stage.members
    roster = tuple(member.role_profile for member in members)
    role_order = tuple(member.role_profile.role for member in members)
    board = (
        InMemoryMemberStatus(role_order=role_order)
        if governance.mandate in _DUTY_MANDATES
        else None
    )
    return LeadStrategy(
        lead=assembly.lead,
        roster=roster,
        board=board,
        delegate_max_attempts=assembly.delegate_max_attempts,
    )


@plugin(
    id="strategy.lead",
    requires=[STRATEGIES.key],
    layer="L3",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description="Register lead TeamStrategy factory.",
    test_suite="tests/test_orchestration_coverage.py",
)
async def setup(ctx: Any, config: Any) -> None:
    del config
    ctx.register(STRATEGIES.key, STRATEGY_KEY_LEAD, build_lead_strategy)
