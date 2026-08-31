"""Fan-out strategy factory — registers into team_strategies."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from lca.contracts.capabilities import STRATEGIES
from lca.contracts.models.team.team_coordination import STRATEGY_KEY_FAN_OUT
from lca.contracts.protocols import TeamAssembly
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


def build_fan_out_strategy(assembly: TeamAssembly) -> Any:
    from lca.cognition.brain.synthesizer import ConcatSynthesizer
    from lca.agent.orchestration_strategies import ParallelStrategy

    return ParallelStrategy(assembly.stage, synthesizer=ConcatSynthesizer())


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="strategy.fan_out",
    requires=[STRATEGIES.key],
    layer="L3",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description="Register fan_out TeamStrategy factory.",
    test_suite="tests/test_parallel_strategy.py",


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G7_EXECUTION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('strategy_fan_out.checked', 'strategy_fan_out.served'),
        revision="v1",
    ),
    relations=(),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    ctx.register(STRATEGIES.key, STRATEGY_KEY_FAN_OUT, build_fan_out_strategy)
