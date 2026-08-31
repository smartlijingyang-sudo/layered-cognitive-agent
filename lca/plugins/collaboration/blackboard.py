"""InMemoryBlackboard plugin — named factory ``blackboard.in-memory``."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-blackboard-memory",
    provides=["blackboard.in-memory"],
    layer="L1",
    effects="none",
    description="Provide InMemoryBlackboard as ``blackboard.in-memory``.",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PRIMITIVE,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G8_COLLAB,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=("memory.read",),
        evidence=("lca-blackboard-memory.checked", "lca-blackboard-memory.served"),
        revision="v1",
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("blackboard.in-memory", "memory.read"),
        emits=("blackboard.in-memory.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide InMemoryBlackboard as ``blackboard.in-memory``."""
    from lca.cognition.collaboration.blackboard import InMemoryBlackboard

    ctx.provide("blackboard.in-memory", InMemoryBlackboard)
