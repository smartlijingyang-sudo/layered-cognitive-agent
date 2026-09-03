"""LoopCursorFactory standard provider (PR-7 / ADR-0169 D8).

把 ``LoopCursorFactory`` 注册为 ``observability.loop_cursor['standard']``。
默认装配(PR-25 阶段统一由 ``lca_kernel.observability.ObservabilityRuntime.from_profile``
通过 capability lookup 取 'standard' 键构造)。

生产路径 = StdLoopCursor(ADR-0169 D1);profile ``observability.loop_cursor.implementation: null``
可切到 null provider。
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
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


@plugin(
    id="observability.loop_cursor.standard",
    requires=["observability.loop_cursor"],
    layer="L1",
    effects="filesystem",
    description="Register LoopCursorFactory as observability.loop_cursor['standard'].",
    test_suite="tests/plugins/observability/test_seam_replacement.py::test_loop_cursor_standard_provider_registers",
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
                "observability.loop_cursor.standard.checked",
                "observability.loop_cursor.standard.served",
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
    """Register :class:`LoopCursorFactory.from_profile` (staticmethod) into the registry.

    The registry entry is the staticmethod itself;Runtime.from_profile will
    call ``factory(profile=..., run_id=..., trace_id=..., spine=...)``
    directly to produce ``(cursor, incarnation)``.
    """
    from lca.infrastructure.observability import NamedRegistry
    from lca.infrastructure.observability.loop_cursor.factory import LoopCursorFactory

    del config
    registry: NamedRegistry = ctx.require("observability.loop_cursor")
    factory = staticmethod(LoopCursorFactory.from_profile)
    registry.register("standard", factory)

    # Mirror the historical "default" alias so capability lookups without
    # explicit provider id still resolve to the standard implementation.
    registry.register("default", factory)