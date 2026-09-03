"""ArtifactClosure Seam Definition plugin — Tier-1."""

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
    id="lca-artifact-closure-seam",
    provides=["artifact_closure"],
    requires=[],
    implements=["ArtifactClosure"],
    layer="L2",
    effects="none",
    kind=PluginKind.SEAM,
    description="Provide the ArtifactClosure Definition service.",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-artifact-closure-seam.checked", "lca-artifact-closure-seam.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("artifact_closure",),
        emits=("artifact_closure.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.plugins.journal.artifact_closure_provider import DefaultArtifactClosure

    ctx.provide("artifact_closure", DefaultArtifactClosure())


__all__ = ["setup"]
