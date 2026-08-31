"""PromptReasoner plugin — named factory ``reasoner.prompt``."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols import Reasoner
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-reasoner-prompt",
    provides=["reasoner.prompt"],
    implements=[Reasoner],
    layer="L1",
    effects="none",
    description="Provide the PromptReasoner class as ``reasoner.prompt``.",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PRIMITIVE,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G5_COGNITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.TURN,
        authority=("plugin.serve",),
        evidence=("lca-reasoner-prompt.checked", "lca-reasoner-prompt.served"),
        revision="v1",
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("reasoner.prompt",),
        emits=("reasoner.prompt.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide the PromptReasoner class as ``reasoner.prompt``.

    ModularBrain still constructs Reasoner internally; this key lets a
    Composer or an alternate Brain factory resolve the Standard reasoner
    without importing layer1.
    """
    from lca.cognition.brain.reasoner import PromptReasoner

    ctx.provide("reasoner.prompt", PromptReasoner)
