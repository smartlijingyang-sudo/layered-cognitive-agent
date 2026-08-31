"""SimpleCritic plugin — named factory ``critic.simple``."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols import Critic
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-critic-simple",
    provides=["critic.simple"],
    implements=[Critic],
    layer="L1",
    effects="none",
    description="Provide SimpleCritic as ``critic.simple``.",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PRIMITIVE,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G5_COGNITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.TURN,
        authority=('plugin.serve',),
        evidence=('lca-critic-simple.checked', 'lca-critic-simple.served'),
        revision="v1",
    ),
    relations=(),

    ownership=OwnershipDeclaration(
        reads=('critic.simple',),
        emits=('critic.simple.checked',),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide SimpleCritic as ``critic.simple``."""
    from lca.cognition.brain.critic import SimpleCritic

    ctx.provide("critic.simple", SimpleCritic)
