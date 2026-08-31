"""ConcatSynthesizer plugin — named factory ``synthesizer.concat``."""

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
from lca.contracts.protocols import Synthesizer
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-synthesizer-concat",
    provides=["synthesizer.concat"],
    implements=[Synthesizer],
    layer="L1",
    effects="none",
    description="Provide ConcatSynthesizer as ``synthesizer.concat``.",
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
            descriptors=("lca-synthesizer-concat.checked", "lca-synthesizer-concat.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("synthesizer.concat",),
        emits=("synthesizer.concat.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide ConcatSynthesizer as ``synthesizer.concat``."""
    from lca.cognition.brain.synthesizer import ConcatSynthesizer

    ctx.provide("synthesizer.concat", ConcatSynthesizer)
