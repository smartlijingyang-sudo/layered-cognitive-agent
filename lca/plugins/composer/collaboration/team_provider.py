"""Profile-visible provider for the plan-bound organization composer."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.plugins.composer.collaboration.team_composer import TeamComposer
from lca.plugins.composer.composition.agent_assembly import PlanBoundAgentAssembler


class Config(BaseModel):
    """Strict configuration for the built-in team composer provider."""

    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-plan-team-composer",
    provides=["composer.team"],
    requires=[],
    implements=["TeamGraphComposer"],
    layer="L4",
    effects="none",
    description="Plan-bound organization composer with a narrow team-graph interface.",
    test_suite="tests/composer/test_composer_consumes_compiled_capability.py",
    kind=PluginKind.PROVIDER,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('lca-plan-team-composer.checked', 'lca-plan-team-composer.served'),
        revision="v1",
    ),
    relations=(),

    ownership=OwnershipDeclaration(
        reads=('composer.team',),
        emits=('composer.team.checked',),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide only the profile-selected organization graph composer."""

    del config
    ctx.provide("composer.team", TeamComposer(PlanBoundAgentAssembler()))


__all__ = ["Config", "setup"]
