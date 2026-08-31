"""LayeredRetrievalPolicy plugin — named factory ``retrieval.layered`` (ADR-0068)."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import MEMORY_RETRIEVAL_POLICY
from lca.contracts.protocols import RetrievalPolicy
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-retrieval-layered",
    provides=["retrieval.layered", MEMORY_RETRIEVAL_POLICY.key],
    implements=[RetrievalPolicy],
    layer="L0",
    effects="none",
    description=(
        "Provide LayeredRetrievalPolicy as ``retrieval.layered``. "
        "Standard bundle upgrades default null retrieval to per-layer weighted."
    ),
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PRIMITIVE,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G3_FACTS,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=("plugin.serve",),
        evidence=("lca-retrieval-layered.checked", "lca-retrieval-layered.served"),
        revision="v1",
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("retrieval.layered",),
        emits=("retrieval.layered.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide LayeredRetrievalPolicy as ``retrieval.layered``."""
    from lca.cognition.memory.layered_retrieval_policy import (
        LayeredRetrievalPolicy,
    )

    ctx.provide("retrieval.layered", LayeredRetrievalPolicy)
    ctx.provide(MEMORY_RETRIEVAL_POLICY.key, LayeredRetrievalPolicy)
