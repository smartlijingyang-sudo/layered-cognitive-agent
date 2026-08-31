"""ComponentRegistry contributor: SimpleMemorySystem (ADR-0074).

Injects the shared ComponentRegistry and registers the simple memory
implementation under ComponentKind.MEMORY.
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.enums import ComponentKind
from lca.contracts.capabilities import COMPONENT_REGISTRY
from lca.contracts.protocols.journal.spec import MEMORY_CHOICE_SIMPLE, MEMORY_CHOICE_TEMPORAL
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-component-memory-contributor",
    provides=[],
    requires=[COMPONENT_REGISTRY.key],
    layer="L4",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="Register simple and temporal MemorySystem implementations into the ComponentRegistry.",
    test_suite="tests/architecture/test_component_registry_seam.py",


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('lca-component-memory-contributor.checked', 'lca-component-memory-contributor.served'),
        revision="v1",
    ),
    relations=(),

    ownership=OwnershipDeclaration(
        reads=('plugin.serve',),
        emits=('plugin.served',),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    from lca.cognition.memory.simple_memory import SimpleMemorySystem
    from lca.cognition.memory.temporal_memory import TemporalMemorySystem

    registry = ctx.require(COMPONENT_REGISTRY.key)
    registry.register(ComponentKind.MEMORY, MEMORY_CHOICE_SIMPLE, SimpleMemorySystem)
    registry.register(ComponentKind.MEMORY, MEMORY_CHOICE_TEMPORAL, TemporalMemorySystem)


__all__ = ["Config", "setup"]
