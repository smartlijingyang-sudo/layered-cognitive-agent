"""Profile-selected admission policy for writes to the simple memory backend."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from lca.contracts.capabilities import MEMORY_WRITE_POLICY
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.cognition.memory.policy import MemoryPolicy, SimpleMemoryPolicy


class Config(BaseModel):
    """Admission threshold selected by the active profile."""

    model_config = ConfigDict(extra="forbid")
    min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)


@plugin(
    id="lca-memory-write-policy-simple",
    provides=[MEMORY_WRITE_POLICY.key],
    requires=[],
    implements=[MemoryPolicy],
    layer="L0",
    effects="none",
    description="Provide a profile-configured SimpleMemoryPolicy for memory write admission.",
    test_suite="tests/architecture/test_memory_policy_capabilities.py",
    kind=PluginKind.PRIMITIVE,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G3_FACTS,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('lca-memory-write-policy-simple.checked', 'lca-memory-write-policy-simple.served'),
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
    """Provide the selected write-admission policy to memory assemblers."""

    ctx.provide(MEMORY_WRITE_POLICY.key, SimpleMemoryPolicy(min_confidence=config.min_confidence))


__all__ = ["Config", "setup"]
