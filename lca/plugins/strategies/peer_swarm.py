"""Peer-swarm strategy factory — registers into team_strategies."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from lca.contracts.capabilities import STRATEGIES
from lca.contracts.models.team.team_coordination import STRATEGY_KEY_PEER_SWARM, PeerSwarm
from lca.contracts.protocols import TeamAssembly
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


def build_peer_swarm_strategy(assembly: TeamAssembly) -> Any:
    from lca.agent.orchestration_strategies import SwarmStrategy

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


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G7_EXECUTION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('strategy_peer_swarm.checked', 'strategy_peer_swarm.served'),
        revision="v1",
    ),
    relations=(),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    ctx.register(STRATEGIES.key, STRATEGY_KEY_PEER_SWARM, build_peer_swarm_strategy)
