"""Pipeline strategy factory — registers into team_strategies.

同文件承载 SequentialStrategy —— CHOREOGRAPHY: A → B → C with output
chaining。
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
from lca.contracts.models.team.team_coordination import STRATEGY_KEY_PIPELINE
from lca.contracts.protocols import TeamAssembly, TeamStage, TeamStrategy
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class SequentialStrategy(TeamStrategy):
    """Chain members in order; each member's output becomes the next task."""

    def __init__(self, stage: TeamStage) -> None:
        self._stage = stage

    async def run(self, objective: str) -> Result:
        return await invoke_members_sequential(
            self._stage, objective, pass_output_as_next_task=True, stop_on_first_completed=False
        )


def build_pipeline_strategy(assembly: TeamAssembly) -> Any:
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
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("strategy_pipeline.checked", "strategy_pipeline.served")
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
    ctx.register(STRATEGIES.key, STRATEGY_KEY_PIPELINE, build_pipeline_strategy)
