"""Peer-swarm strategy factory — registers into team_strategies."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from lca.contracts.capabilities import STRATEGIES
from lca.contracts.models.team.team_coordination import STRATEGY_KEY_PEER_SWARM, PeerSwarm
from lca.contracts.protocols import TeamAssembly
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


def build_peer_swarm_strategy(assembly: TeamAssembly) -> Any:
    from lca.layer3_agent.orchestration_strategies import SwarmStrategy

    governance = assembly.governance
    if not isinstance(governance, PeerSwarm):
        raise TypeError(f"strategy {STRATEGY_KEY_PEER_SWARM!r} requires PeerSwarm governance")
    return SwarmStrategy(assembly.stage, max_rounds=governance.max_rounds)


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="strategy.peer_swarm",
    requires=[STRATEGIES.key],
    layer="L3",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description="Register peer_swarm TeamStrategy factory.",
    test_suite="tests/test_orchestration_coverage.py",
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    ctx.register(STRATEGIES.key, STRATEGY_KEY_PEER_SWARM, build_peer_swarm_strategy)
