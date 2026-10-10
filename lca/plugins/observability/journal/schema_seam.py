"""JournalSchema seam plugin (Tier-1) —— ADR-0096 MVA-1.

声明 ``journal_schemas`` 注册中心；boot 后 ``providers/journal_schema/v2``
注入 ``EnvelopeV2`` 实现。新增 schema 版本 = 新增 provider + 注册一行。
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.observability.schemas.journal_schema_registry import (
    JournalSchemaRegistry,
    install_journal_schema_registry,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-journal-schema-seam",
    provides=["journal_schemas"],
    requires=[],
    layer="L0",
    effects="none",
    description="Provide the journal_schemas registry (ADR-0096 MVA-1).",
    test_suite="tests/scenario/journal_2/test_journal_schema_seam.py::test_journal_schema_seam_provides_registry",
    kind=PluginKind.SEAM,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-journal-schema-seam.checked", "lca-journal-schema-seam.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("journal_schemas",),
        emits=("journal_schemas.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.contracts.observability.schemas.envelope_v2_schema import (
        EnvelopeV2Schema,
    )

    registry = JournalSchemaRegistry()
    registry.register("v2.0.0", EnvelopeV2Schema())
    install_journal_schema_registry(registry)
    ctx.provide("journal_schemas", registry)
