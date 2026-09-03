"""PersistenceCoordinator null provider (PR-7 / ADR-0169 D8).

把 :class:`NullPersistenceCoordinator`(no-op 持久化协同器)注册为
``observability.persistence['null']``。默认装配 —— 调用方未注入
``FilePersistenceCoordinator`` 时由
:class:`~lca_kernel.observability.ObservabilityRuntime.from_profile`
fallback 到此 provider(barrier 注入面永不空, ADR-0169 D8)。
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


def _make_null_persistence(**_: Any) -> Any:
    """Build a :class:`NullPersistenceCoordinator` (no-op)."""
    from lca.infrastructure.observability.loop_cursor.persistence_coordinator import (
        NullPersistenceCoordinator,
    )

    return NullPersistenceCoordinator()


@plugin(
    id="observability.persistence.null",
    requires=["observability.persistence"],
    layer="L1",
    effects="none",
    description="Register NullPersistenceCoordinator factory as observability.persistence['null'].",
    test_suite="tests/plugins/observability/test_seam_replacement.py::test_persistence_null_provider_registers",
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
                "observability.persistence.null.checked",
                "observability.persistence.null.served",
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
    """Register the null factory; default key resolved by from_profile."""
    from lca.infrastructure.observability import NamedRegistry

    del config
    registry: NamedRegistry = ctx.require("observability.persistence")
    registry.register("null", _make_null_persistence)
    registry.register("default", _make_null_persistence)