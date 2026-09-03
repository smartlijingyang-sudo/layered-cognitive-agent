"""ProjectionHost seam plugin (PR-7 / ADR-0169 D8 五缝 + ADR-0170 D2).

声明 ``observability.projection_host`` 注册中心；boot 后
``providers/projection_host/standard`` 把 ``StdProjectionHost`` factory
注入。Profile 通过 capability lookup 在
:class:`~lca_kernel.observability.ObservabilityRuntime.from_profile`
里拿到选中 provider 并实例化。
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
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="observability.projection_host",
    provides=["observability.projection_host"],
    layer="L1",
    effects="none",
    description="Provide the observability.projection_host seam (ADR-0169 D8 + ADR-0170 D2).",
    test_suite="tests/plugins/observability/test_seam_replacement.py::test_seam_provides_registry",
    kind=PluginKind.SEAM,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "observability.projection_host.checked",
                "observability.projection_host.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("observability.projection_host",),
        emits=("observability.projection_host.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide ``NamedRegistry`` keyed by provider id."""
    from lca.infrastructure.observability import NamedRegistry

    del config
    ctx.provide("observability.projection_host", NamedRegistry())