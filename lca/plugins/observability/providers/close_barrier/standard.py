"""CloseBarrier standard provider (PR-7 / ADR-0169 D5 + D8).

把 :class:`StdCloseBarrier`(默认 close 时序协同器)注册为
``observability.close_barrier['standard']``。close 时由
:class:`~lca_kernel.observability.ObservabilityRuntime.from_profile`
按 ``persistence / host / close_emitter`` 装配注入。
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


def _make_close_barrier(persistence: Any, host: Any, close_emitter: Any, **_: Any) -> Any:
    """Build a :class:`StdCloseBarrier` with the runtime-supplied collaborators."""
    from lca.infrastructure.observability.loop_cursor.close_barrier_impl import StdCloseBarrier

    return StdCloseBarrier(
        persistence=persistence,
        host=host,
        close_emitter=close_emitter,
    )


@plugin(
    id="observability.close_barrier.standard",
    requires=["observability.close_barrier"],
    layer="L1",
    effects="none",
    description="Register StdCloseBarrier factory as observability.close_barrier['standard'].",
    test_suite="tests/plugins/observability/test_seam_replacement.py::test_close_barrier_standard_provider_registers",
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
                "observability.close_barrier.standard.checked",
                "observability.close_barrier.standard.served",
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
    """Register the standard factory; ``from_profile`` passes collaborators per call."""
    from lca.infrastructure.observability import NamedRegistry

    del config
    registry: NamedRegistry = ctx.require("observability.close_barrier")
    registry.register("standard", _make_close_barrier)
    registry.register("default", _make_close_barrier)