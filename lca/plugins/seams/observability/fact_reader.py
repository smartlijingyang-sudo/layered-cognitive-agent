"""Fact reader seam plugin (Tier-1).

声明 ``fact_readers`` 注册中心；boot 后 ``providers/fact_reader`` 把各种
``JournalProjector`` factory 注入。新增 fact reader = 新增 provider + 注册一行。
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
from lca.contracts.protocols import JournalProjector
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-fact-reader-seam",
    provides=["fact_readers"],
    implements=[JournalProjector],
    layer="L0",
    effects="none",
    description="Provide the fact_readers seam (facade plugin-ification).",
    test_suite="tests/test_fact_reader_plugin.py::test_seam_provides_registry",
    kind=PluginKind.SEAM,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-fact-reader-seam.checked", "lca-fact-reader-seam.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("fact_readers",),
        emits=("fact_readers.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.observability import NamedRegistry

    ctx.provide("fact_readers", NamedRegistry())
