"""ModelVisibleCapture seam plugin (PR-7 / ADR-0169 D7 + ADR-0169 D8 五缝).

声明 ``observability.model_visible`` 注册中心；boot 后
``providers/model_visible_capture/standard`` 把 ``StdModelVisibleCapture``
factory 注入。Profile 通过 capability lookup 在
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
    id="observability.model_visible",
    provides=["observability.model_visible"],
    layer="L1",
    effects="filesystem",
    description="Provide the observability.model_visible seam (ADR-0169 D7 + D8 五缝).",
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
                "observability.model_visible.checked",
                "observability.model_visible.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("observability.model_visible",),
        emits=("observability.model_visible.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide ``NamedRegistry`` keyed by provider id."""
    from lca.infrastructure.observability import NamedRegistry

    del config
    ctx.provide("observability.model_visible", NamedRegistry())