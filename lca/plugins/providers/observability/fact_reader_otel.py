"""OtelProjector factory plugin (Tier-2).

把 ``OtelProjector`` 注册为 ``fact_readers`` 的 factory。
tracer 实例由 assemble 阶段按 kwarg 注入（典型来源：tracer_backend 工厂产物）。
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
    id="lca-fact-reader-otel-factory",
    requires=["fact_readers"],
    implements=[JournalProjector],
    layer="L0",
    effects="none",
    description="Register OtelProjector factory as fact_readers['otel'].",
    test_suite="tests/test_fact_reader_plugin.py::test_provider_registers_otel_reader",
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
                "lca-fact-reader-otel-factory.checked",
                "lca-fact-reader-otel-factory.served",
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
    from lca.infrastructure.observability.journal.otel.projector import OtelProjector

    registry: NamedRegistry = ctx.require("fact_readers")

    def _make_otel_reader(
        settings: ObservabilitySettings | None = None,
        *,
        tracer: Any = None,
        **_: Any,
    ) -> JournalProjector:
        # tracer 由 assemble 阶段按 kwarg 注入；此处不主动构造
        _ = settings
        return OtelProjector(tracer, genai_mapper_registry=None)

    registry.register("otel", _make_otel_reader)
