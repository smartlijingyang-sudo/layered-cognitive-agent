"""LoopCursorFactory seam plugin (PR-7 / ADR-0169 D8 五缝).

声明 ``observability.loop_cursor`` 注册中心；boot 后
``providers/loop_cursor/standard`` 与 ``providers/loop_cursor/null``
按 profile 选择把 factory 类注入。Profile 通过 capability lookup 在
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
    id="observability.loop_cursor.factory",
    provides=["observability.loop_cursor"],
    layer="L1",
    effects="none",
    description="Provide the observability.loop_cursor seam (ADR-0169 D8 五缝).",
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
                "observability.loop_cursor.factory.checked",
                "observability.loop_cursor.factory.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("observability.loop_cursor",),
        emits=("observability.loop_cursor.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide ``NamedRegistry`` keyed by provider id (standard / null)."""
    from lca.infrastructure.observability import NamedRegistry

    del config
    ctx.provide("observability.loop_cursor", NamedRegistry())