"""Peer-relay strategy factory — registers into team_strategies.

同文件承载 RaceStrategy —— PEER: sequential try, first COMPLETED wins
(no output chaining)。

命名说明：旧名 HandoffStrategy 与 ActionType.HANDOFF（非阻塞 body action）
概念冲突，重命名为 RaceStrategy 以准确表达"竞速"语义。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from lca.agent.member_invoke import invoke_members_sequential
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import STRATEGIES
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.result import Result
from lca.contracts.models.team.team_coordination import STRATEGY_KEY_PEER_RELAY
from lca.contracts.protocols import TeamAssembly, TeamStage, TeamStrategy
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class RaceStrategy(TeamStrategy):
    """PEER topology: stop at the first member that completes."""

    def __init__(self, stage: TeamStage) -> None:
        self._stage = stage

    async def run(self, objective: str) -> Result:
        return await invoke_members_sequential(
            self._stage,
            objective,
            pass_output_as_next_task=False,
            stop_on_first_completed=True,
        )


# 向后兼容别名（下一大版本移除）
HandoffStrategy = RaceStrategy


def build_peer_relay_strategy(assembly: TeamAssembly) -> Any:
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
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("strategy_peer_relay.checked", "strategy_peer_relay.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    ctx.register(STRATEGIES.key, STRATEGY_KEY_PEER_RELAY, build_peer_relay_strategy)
