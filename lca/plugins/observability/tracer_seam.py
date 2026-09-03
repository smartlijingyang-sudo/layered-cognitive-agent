"""Tracer seam plugin (Tier-1).

声明 ``tracer_backends`` 注册中心；boot 后 ``providers/otel_tracer`` 把
``OtelTracer`` factory 注入。新增 tracer backend = 新增 provider + 注册一行。
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
from lca.contracts.observability.ports import TracerBackend
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-tracer-seam",
    provides=["tracer_backends"],
    implements=[TracerBackend],
    layer="L0",
    effects="none",
    description="Provide the tracer_backends seam (facade plugin-ification).",
    test_suite="tests/test_tracer_plugin.py::test_seam_provides_registry",
    kind=PluginKind.SEAM,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-tracer-seam.checked", "lca-tracer-seam.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("tracer_backends",),
        emits=("tracer_backends.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.observability import NamedRegistry

    ctx.provide("tracer_backends", NamedRegistry())
