"""NullRetrievalPolicy plugin — named factory ``retrieval.null`` (ADR-0068 / 宪法 §3.4)."""

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
    id="lca-retrieval-null",
    provides=["retrieval.null", MEMORY_RETRIEVAL_POLICY.key],
    implements=[RetrievalPolicy],
    layer="L0",
    effects="none",
    description=(
        "Provide NullRetrievalPolicy as ``retrieval.null`` (ADR-0068 default). "
        "Profile without standard-memory bundle ships empty retrieved_context."
    ),
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PRIMITIVE,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G3_FACTS,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=("plugin.serve",),
        evidence=("lca-retrieval-null.checked", "lca-retrieval-null.served"),
        revision="v1",
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("retrieval.null",),
        emits=("retrieval.null.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide NullRetrievalPolicy as ``retrieval.null``."""
    from lca.cognition.memory.null_retrieval_policy import NullRetrievalPolicy

    ctx.provide("retrieval.null", NullRetrievalPolicy)
    ctx.provide(MEMORY_RETRIEVAL_POLICY.key, NullRetrievalPolicy)
