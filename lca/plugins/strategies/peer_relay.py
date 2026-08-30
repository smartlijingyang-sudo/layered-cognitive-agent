"""Peer-relay strategy factory — registers into team_strategies."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from lca.contracts.capabilities import STRATEGIES
from lca.contracts.models.team.team_coordination import STRATEGY_KEY_PEER_RELAY
from lca.contracts.protocols import TeamAssembly
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


def build_peer_relay_strategy(assembly: TeamAssembly) -> Any:
    from lca.agent.orchestration_strategies import RaceStrategy

    return RaceStrategy(assembly.stage)


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="strategy.peer_relay",
    requires=[STRATEGIES.key],
    layer="L3",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description="Register peer_relay TeamStrategy factory.",
    test_suite="tests/test_handoff_strategy.py",
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    ctx.register(STRATEGIES.key, STRATEGY_KEY_PEER_RELAY, build_peer_relay_strategy)
