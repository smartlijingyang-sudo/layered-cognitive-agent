"""Runtime-lifecycle subscriber registry seam.

The seam creates an empty neutral registry only. Provider plugins independently
contribute passive subscribers at profile boot, while a single composite provider
freezes the registry into the runtime binding before any Agent Loop executes.
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import RUNTIME_LIFECYCLE_SUBSCRIBER_REGISTRY
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.runtime.runtime_lifecycle import RuntimeLifecycleSubscriberRegistry
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.runtime.runtime_event_publisher import InMemoryRuntimeLifecycleSubscriberRegistry


class Config(BaseModel):
    """The neutral registry has no configurable behavior."""

    model_config = {"extra": "forbid"}


@plugin(
    id="lca-runtime-lifecycle-subscriber-registry-seam",
    Config=Config,
    provides=[RUNTIME_LIFECYCLE_SUBSCRIBER_REGISTRY.key],
    requires=[],
    implements=[RuntimeLifecycleSubscriberRegistry],
    layer="L2",
    effects="none",
    description="Provide the neutral registry for passive Agent Loop lifecycle subscribers.",
    test_suite="tests/runtime/test_runtime_lifecycle_plugins.py",
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
                "lca-runtime-lifecycle-subscriber-registry-seam.checked",
                "lca-runtime-lifecycle-subscriber-registry-seam.served",
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
async def setup(ctx: PluginContext, config: BaseModel) -> None:
    """Mount an empty registry; contributor providers register all behavior."""

    del config
    ctx.provide(
        RUNTIME_LIFECYCLE_SUBSCRIBER_REGISTRY.key,
        InMemoryRuntimeLifecycleSubscriberRegistry(),
    )


__all__ = [
    "Config",
    "InMemoryRuntimeLifecycleSubscriberRegistry",
    "RuntimeLifecycleSubscriberRegistry",
    "setup",
]
