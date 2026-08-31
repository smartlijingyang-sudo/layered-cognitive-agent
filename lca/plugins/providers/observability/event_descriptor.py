"""EventDescriptor bootstrap plugin (Tier-2) —— ADR-0063 PR-7.

把 ``event_descriptors_data.build_default_registry()`` 的 49 个内置
``EventDescriptor`` 注入 ``event_descriptor_registry`` seam。
"""

from __future__ import annotations

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
from lca.contracts.observability.event_descriptor_registry import EventDescriptorRegistry
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-event-descriptor-bootstrap",
    requires=["event_descriptor_registry"],
    implements=[EventDescriptorRegistry],
    layer="L0",
    effects="none",
    description="Bootstrap 49 builtin EventDescriptor into the registry.",
    test_suite="tests/test_event_descriptor_registry.py::test_bootstrap_registers_builtin_descriptors",
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
                "lca-event-descriptor-bootstrap.checked",
                "lca-event-descriptor-bootstrap.served",
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
    from lca.infrastructure.observability import build_default_registry

    registry = ctx.require("event_descriptor_registry")
    bootstrap = build_default_registry()
    for descriptor in bootstrap:
        registry.register(descriptor, replace=False)
