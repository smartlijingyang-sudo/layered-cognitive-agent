"""SimpleBrain strategy plugin — registers into BRAINS as 'default'."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import BRAINS
from lca.contracts.protocols import BrainFactory
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.brain._standard_factory import (
    STANDARD_COGNITIVE_BRAIN_FACTORY_REQUIREMENTS,
    build_standard_cognitive_brain_factory,
)


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-brain-simple",
    provides=[],
    requires=STANDARD_COGNITIVE_BRAIN_FACTORY_REQUIREMENTS,
    implements=[BrainFactory],
    layer="L1",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    functional_group=FunctionalGroup.G5_COGNITION,
    description="Register the standard cognitive Brain factory as brains['default'].",
    test_suite="tests/test_plugin_alignment.py",
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G5_COGNITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.TURN,
        authority=("plugin.serve",),
        evidence=("lca-brain-simple.checked", "lca-brain-simple.served"),
        revision="v1",
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
    factory = build_standard_cognitive_brain_factory(ctx)
    ctx.register(BRAINS.key, "default", factory)
