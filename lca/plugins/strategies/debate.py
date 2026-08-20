"""Debate strategy factory — registers into team_strategies."""

from __future__ import annotations

from typing import Any

from lca.contracts.capabilities import STRATEGIES
from lca.contracts.models.team.team_coordination import STRATEGY_KEY_DEBATE, Debate
from lca.contracts.protocols import TeamAssembly
from lca.harness.plugin_api import PluginKind, plugin


def build_debate_strategy(assembly: TeamAssembly) -> Any:
    from lca.layer3_agent.orchestration_strategies import DebateStrategy

    governance = assembly.governance
    if not isinstance(governance, Debate):
        raise TypeError(f"strategy {STRATEGY_KEY_DEBATE!r} requires Debate governance")
    return DebateStrategy(assembly.stage, max_rounds=governance.max_rounds)


@plugin(
    id="strategy.debate",
    requires=[STRATEGIES.key],
    layer="L3",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description="Register debate TeamStrategy factory.",
    test_suite="tests/test_debate_strategy.py",
)
async def setup(ctx: Any, config: Any) -> None:
    del config
    ctx.register(STRATEGIES.key, STRATEGY_KEY_DEBATE, build_debate_strategy)
