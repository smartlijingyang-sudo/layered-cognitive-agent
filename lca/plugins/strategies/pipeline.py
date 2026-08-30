"""Pipeline strategy factory — registers into team_strategies."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from lca.contracts.capabilities import STRATEGIES
from lca.contracts.models.team.team_coordination import STRATEGY_KEY_PIPELINE
from lca.contracts.protocols import TeamAssembly
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


def build_pipeline_strategy(assembly: TeamAssembly) -> Any:
    from lca.agent.orchestration_strategies import SequentialStrategy

    return SequentialStrategy(assembly.stage)


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="strategy.pipeline",
    requires=[STRATEGIES.key],
    layer="L3",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description="Register pipeline TeamStrategy factory.",
    test_suite="tests/test_orchestration_coverage.py",
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    ctx.register(STRATEGIES.key, STRATEGY_KEY_PIPELINE, build_pipeline_strategy)
