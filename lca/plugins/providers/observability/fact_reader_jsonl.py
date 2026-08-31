"""JsonlJournalProjector factory plugin (Tier-2).

把 ``JsonlJournalProjector`` 注册为 ``fact_readers`` 的 factory。
journal 事件逐行 JSON 落盘，路径取自 ``settings.jsonl_path``。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

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
    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-fact-reader-jsonl-factory",
    requires=["fact_readers"],
    implements=[JournalProjector],
    layer="L0",
    effects="filesystem",
    description="Register JsonlJournalProjector factory as fact_readers['jsonl'].",
    test_suite="tests/test_fact_reader_plugin.py::test_provider_registers_jsonl_reader",
    kind=PluginKind.PROVIDER,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lca-fact-reader-jsonl-factory.checked",
                "lca-fact-reader-jsonl-factory.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.observability import NamedRegistry, ObservabilitySettings
    from lca.infrastructure.observability.journal.jsonl.projector import (
        JsonlJournalProjector,
    )

    registry: NamedRegistry = ctx.require("fact_readers")

    def _make_jsonl(settings: ObservabilitySettings | None = None, **_: Any) -> JournalProjector:
        cfg = settings or ObservabilitySettings()
        return JsonlJournalProjector(output_path=cfg.jsonl_path)

    registry.register("jsonl", _make_jsonl)
