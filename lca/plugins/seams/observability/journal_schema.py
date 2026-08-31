"""JournalSchema seam plugin (Tier-1) —— ADR-0096 MVA-1.

声明 ``journal_schemas`` 注册中心；boot 后 ``providers/journal_schema/v2``
注入 ``EnvelopeV2`` 实现。新增 schema 版本 = 新增 provider + 注册一行。
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.observability.schemas.v2 import JournalSchema
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


class JournalSchemaRegistry:
    """Named registry of JournalSchema implementations.

    Task 1 used a placeholder; Task 3 registers ``schema-v2.0.0`` at boot.
    """

    def __init__(self) -> None:
        self._schemas: dict[str, JournalSchema] = {}

    def name(self) -> str:
        return "JournalSchemaRegistry"

    def register(self, version: str, schema: JournalSchema) -> None:
        self._schemas[version] = schema

    def get(self, version: str) -> JournalSchema | None:
        return self._schemas.get(version)

    def all(self) -> dict[str, JournalSchema]:
        return dict(self._schemas)


@plugin(
    id="lca-journal-schema-seam",
    provides=["journal_schemas"],
    requires=[],
    layer="L0",
    effects="none",
    description="Provide the journal_schemas registry (ADR-0096 MVA-1).",
    test_suite="tests/test_journal_schema_seam.py::test_journal_schema_seam_provides_registry",
    kind=PluginKind.SEAM,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=("plugin.serve",),
        evidence=("lca-journal-schema-seam.checked", "lca-journal-schema-seam.served"),
        revision="v1",
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("journal_schemas",),
        emits=("journal_schemas.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.plugins.providers.journal_schema.v2 import EnvelopeV2Schema

    registry = JournalSchemaRegistry()
    registry.register("v2.0.0", EnvelopeV2Schema())
    ctx.provide("journal_schemas", registry)
