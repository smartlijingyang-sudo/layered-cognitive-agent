"""Debate strategy factory — registers into team_strategies."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

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
from lca.contracts.models.team.team_coordination import STRATEGY_KEY_DEBATE, Debate
from lca.contracts.protocols import TeamAssembly
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


def build_debate_strategy(assembly: TeamAssembly) -> Any:
    from lca.agent.orchestration_strategies import DebateStrategy

    governance = assembly.governance
    if not isinstance(governance, Debate):
        raise TypeError(f"strategy {STRATEGY_KEY_DEBATE!r} requires Debate governance")
    return DebateStrategy(assembly.stage, max_rounds=governance.max_rounds)


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="strategy.debate",
    requires=[STRATEGIES.key],
    layer="L3",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description="Register debate TeamStrategy factory.",
    test_suite="tests/test_debate_strategy.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("strategy_debate.checked", "strategy_debate.served")
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
    ctx.register(STRATEGIES.key, STRATEGY_KEY_DEBATE, build_debate_strategy)
