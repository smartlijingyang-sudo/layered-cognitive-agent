"""NullCritic plugin — named factory ``critic.null`` (ADR-0068 / 宪法 §3.4)."""

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
    id="lca-critic-null",
    provides=["critic.null"],
    implements=[Critic],
    layer="L1",
    effects="none",
    description="Provide NullCritic as ``critic.null`` (ADR-0068 default).",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PRIMITIVE,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G5_COGNITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.TURN,
        authority=('plugin.serve',),
        evidence=('lca-critic-null.checked', 'lca-critic-null.served'),
        revision="v1",
    ),
    relations=(),

    ownership=OwnershipDeclaration(
        reads=('critic.null',),
        emits=('critic.null.checked',),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide NullCritic as ``critic.null``."""
    from lca.cognition.brain.null_critic import NullCritic

    ctx.provide("critic.null", NullCritic)
