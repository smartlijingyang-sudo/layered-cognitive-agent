"""Graph strategy factory — registers into team_strategies."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from lca.contracts.capabilities import STRATEGIES
from lca.contracts.models.team.team_coordination import STRATEGY_KEY_GRAPH, Graph
from lca.contracts.protocols import TeamAssembly
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


def build_graph_strategy(assembly: TeamAssembly) -> Any:
    from lca.layer3_agent.orchestration_strategies import GraphStrategy

    governance = assembly.governance
    if not isinstance(governance, Graph):
        raise TypeError(f"strategy {STRATEGY_KEY_GRAPH!r} requires Graph governance")
    return GraphStrategy(assembly.stage, execution_graph=governance.execution_graph)


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="strategy.graph",
    requires=[STRATEGIES.key],
    layer="L3",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description="Register graph TeamStrategy factory.",
    test_suite="tests/test_graph_strategy.py",
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    ctx.register(STRATEGIES.key, STRATEGY_KEY_GRAPH, build_graph_strategy)
