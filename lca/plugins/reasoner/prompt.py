"""PromptReasoner plugin — named factory ``reasoner.prompt``."""

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
from lca.contracts.protocols import Reasoner
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
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G5_COGNITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.TURN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-reasoner-prompt.checked", "lca-reasoner-prompt.served")
        ),
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
