"""ProjectionHost standard provider (PR-7 / ADR-0169 D8 + ADR-0170 D2).

把 :class:`StdProjectionHost`(默认 ProjectionHost 实现, ADR-0170 D2)
注册为 ``observability.projection_host['standard']``。
profile 装配阶段 :class:`~lca_kernel.observability.ObservabilityRuntime.from_profile`
按 ``observability.projection_host.initial`` 列表传给 host(PR-25 key hint 模式)。
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
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _make_projection_host(initial: list[Any] | None = None, **_: Any) -> Any:
    """Build a :class:`StdProjectionHost` with the profile-supplied initial deriver list."""
    from lca.infrastructure.observability.loop_cursor.projection_host import StdProjectionHost

    return StdProjectionHost(initial=initial)


@plugin(
    id="observability.projection_host.standard",
    requires=["observability.projection_host"],
    layer="L1",
    effects="none",
    description="Register StdProjectionHost factory as observability.projection_host['standard'].",
    test_suite="tests/plugins/observability/test_seam_replacement.py::test_projection_host_standard_provider_registers",
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
                "observability.projection_host.standard.checked",
                "observability.projection_host.standard.served",
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
    """Register the standard factory; ``from_profile`` passes ``initial`` per call."""
    from lca.infrastructure.observability import NamedRegistry

    del config
    registry: NamedRegistry = ctx.require("observability.projection_host")
    registry.register("standard", _make_projection_host)
    registry.register("default", _make_projection_host)