"""Peer-swarm strategy factory — registers into team_strategies.

同文件承载 SwarmStrategy —— PEER: round-robin peers with context
accumulation。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.atoms.telemetry import ATTR_MAX_ROUNDS, ATTR_ROUND, SpanName
from lca.contracts.capabilities import STRATEGIES
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.result import Result
from lca.contracts.models.team.team_coordination import STRATEGY_KEY_PEER_SWARM, PeerSwarm
from lca.contracts.protocols import TeamAssembly, TeamStage, TeamStrategy
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.observability import span


class SwarmStrategy(TeamStrategy):
    """Round-robin peers; accumulate peer updates until success or budget."""

    def __init__(self, stage: TeamStage, max_rounds: int) -> None:
        self._stage = stage
        self._max_rounds = max_rounds

    async def run(self, objective: str) -> Result:
        members = self._stage.members
        if not members:
            return Result.failed("No members in team")

        current = objective
        total_steps = 0
        last: Result | None = None
        for round_idx in range(self._max_rounds):
            with span(
                SpanName.TEAM_ROUND,
                **{ATTR_ROUND: round_idx, ATTR_MAX_ROUNDS: self._max_rounds},
            ):
                for member in members:
                    last = await self._stage.invoker.invoke(member, current)
                    total_steps += last.total_steps
                    if last.status == TaskStatus.COMPLETED and last.output:
                        last.total_steps = total_steps
                        return last
                    if last.output:
                        role = member.role_profile.role or "peer"
                        current = f"{objective}\n\nPeer update ({role}):\n{last.output}"
        if last is None:
            return Result.failed("No members in team")
        last.total_steps = total_steps
        return last


def build_peer_swarm_strategy(assembly: TeamAssembly) -> Any:
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
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("strategy_peer_swarm.checked", "strategy_peer_swarm.served")
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
    ctx.register(STRATEGIES.key, STRATEGY_KEY_PEER_SWARM, build_peer_swarm_strategy)
