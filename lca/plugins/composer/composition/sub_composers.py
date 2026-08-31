"""Profile-visible plan sub-composer provider."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.composer.act.body_composer import BodyComposer
from lca.plugins.composer.collaboration.team_composer import TeamComposer
from lca.plugins.composer.composition.agent_assembly import PlanBoundAgentAssembler
from lca.plugins.composer.perceive.perceive_composer import PerceiveComposer
from lca.plugins.composer.think.brain_composer import BrainComposer


class Config(BaseModel):
    """Strict configuration for the built-in plan composer provider."""

    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-plan-sub-composers",
    provides=["composer.brain", "composer.body", "composer.perceive", "composer.team"],
    requires=[],
    implements=["AgentGraphComposer", "TeamGraphComposer"],
    layer="L4",
    effects="none",
    description="Plan-bound AgentGraph and TeamGraph composers with narrow interfaces.",
    test_suite="tests/application/test_spawn_bind_plan.py",
    kind=PluginKind.PROVIDER,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=("context.read",),
        evidence=("lca-plan-sub-composers.checked", "lca-plan-sub-composers.served"),
        revision="v1",
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("composer.body", "composer.brain", "composer.perceive", "composer.team"),
        emits=(
            "composer.brain.checked",
            "composer.body.checked",
            "composer.perceive.checked",
            "composer.team.checked",
        ),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide the complete set of plan composers to the booted Profile scope."""

    del config
    ctx.provide("composer.brain", BrainComposer())
    ctx.provide("composer.body", BodyComposer())
    ctx.provide("composer.perceive", PerceiveComposer())
    ctx.provide("composer.team", TeamComposer(PlanBoundAgentAssembler()))


__all__ = ["Config", "setup"]
