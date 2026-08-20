"""Fan-out strategy factory — registers into team_strategies."""

from __future__ import annotations

from typing import Any

from lca.contracts.capabilities import STRATEGIES
from lca.contracts.models.team.team_coordination import STRATEGY_KEY_FAN_OUT
from lca.contracts.protocols import TeamAssembly
from lca.harness.plugin_api import PluginKind, plugin


def build_fan_out_strategy(assembly: TeamAssembly) -> Any:
    from lca.layer1_cognitive.brain.synthesizer import ConcatSynthesizer
    from lca.layer3_agent.orchestration_strategies import ParallelStrategy

    return ParallelStrategy(assembly.stage, synthesizer=ConcatSynthesizer())


@plugin(
    id="strategy.fan_out",
    requires=[STRATEGIES.key],
    layer="L3",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description="Register fan_out TeamStrategy factory.",
    test_suite="tests/test_parallel_strategy.py",
)
async def setup(ctx: Any, config: Any) -> None:
    del config
    ctx.register(STRATEGIES.key, STRATEGY_KEY_FAN_OUT, build_fan_out_strategy)
