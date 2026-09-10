"""Default ``runtime_lifecycle_publisher`` capability provider.

Registers the null lifecycle publisher so the interpreter can publish
turn-boundary events without forcing a profile to contribute at least
one structured subscriber.  Production profiles are expected to swap
this with a composite publisher backed by telemetry sinks.
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.runtime.runtime.lifecycle import RuntimeLifecyclePublisher
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.runtime.loop.runtime_event_publisher import NullRuntimeLifecyclePublisher


class Config(BaseModel):
    """The default null publisher has no deployment-specific settings."""

    model_config = {"extra": "forbid"}


@plugin(
    id="declarative.runtime_lifecycle_publisher",
    requires=[],
    provides=["runtime_lifecycle_publisher"],
    implements=[RuntimeLifecyclePublisher],
    layer="L2",
    effects="none",
    kind=PluginKind.PROVIDER,
    description=(
        "Provide the default null RuntimeLifecyclePublisher so declarative "
        "profiles have a passive turn-boundary seam until a telemetry-backed "
        "publisher replaces it."
    ),
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "declarative.runtime_lifecycle_publisher.checked",
                "declarative.runtime_lifecycle_publisher.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("runtime_lifecycle_publisher",),
        emits=("runtime_lifecycle_publisher.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Expose the default null RuntimeLifecyclePublisher to runtime assembly."""

    del config
    ctx.provide("runtime_lifecycle_publisher", NullRuntimeLifecyclePublisher())


__all__ = ["Config", "setup"]
