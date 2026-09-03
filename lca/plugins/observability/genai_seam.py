"""GenAI semantic mapper seam plugin (Tier-1) —— ADR-0063 PR-10.

声明 ``genai_semantic_mapper`` 服务形状；boot 后 ``providers/genai_*`` 注册
LLM / Tool / Code / Permission / Retry 五个 mapper。
"""

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
from lca.contracts.observability.genai_semantic import GenAISemanticMapper
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-genai-semantic-mapper-seam",
    provides=["genai_semantic_mapper"],
    implements=[GenAISemanticMapper],
    layer="L0",
    effects="none",
    description="Provide the GenAI semantic mapper seam (PR-10).",
    test_suite="tests/test_genai_semantic.py::test_seam_provides_registry",
    kind=PluginKind.SEAM,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lca-genai-semantic-mapper-seam.checked",
                "lca-genai-semantic-mapper-seam.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("genai_semantic_mapper",),
        emits=("genai_semantic_mapper.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.observability import NamedRegistry

    ctx.provide("genai_semantic_mapper", NamedRegistry())
