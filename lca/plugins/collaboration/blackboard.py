"""InMemoryBlackboard plugin — named factory ``blackboard.in-memory``."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
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
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G8_COLLAB, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("memory.read",)),
        observability=EvidenceContract(
            descriptors=("lca-blackboard-memory.checked", "lca-blackboard-memory.served")
        ),
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
