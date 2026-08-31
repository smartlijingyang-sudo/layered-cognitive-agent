"""Default structured-log contribution for Agent Loop lifecycle events."""

from __future__ import annotations

from pydantic import BaseModel, Field

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
from lca.contracts.protocols.runtime.runtime_lifecycle import (
    RuntimeLifecycleSubscriber,
    RuntimeLifecycleSubscriberContribution,
    RuntimeLifecycleSubscriberRegistry,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.runtime.runtime_event_publisher import StructuredLogRuntimeLifecycleSubscriber


class Config(BaseModel):
    """Configure the logging subscriber's deterministic precedence."""

    priority: int = Field(default=100, ge=0)
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-runtime-lifecycle-logging-provider",
    Config=Config,
    provides=[],
    requires=[RUNTIME_LIFECYCLE_SUBSCRIBER_REGISTRY.key],
    implements=[RuntimeLifecycleSubscriber],
    layer="L2",
    effects="none",
    description="Contribute structured Agent Loop lifecycle logging without control access.",
    test_suite="tests/runtime/test_runtime_lifecycle_plugins.py",
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
                "lca-runtime-lifecycle-logging-provider.checked",
                "lca-runtime-lifecycle-logging-provider.served",
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
    """Register lifecycle logging without becoming the runtime publisher itself."""

    if not isinstance(config, Config):
        raise TypeError("runtime lifecycle logging config must be Config")
    registry = ctx.require(RUNTIME_LIFECYCLE_SUBSCRIBER_REGISTRY)
    if not isinstance(registry, RuntimeLifecycleSubscriberRegistry):
        raise TypeError(
            "runtime_lifecycle_subscriber_registry must implement "
            "RuntimeLifecycleSubscriberRegistry"
        )
    registry.register(
        RuntimeLifecycleSubscriberContribution(
            id="structured-log",
            subscriber=StructuredLogRuntimeLifecycleSubscriber(),
            priority=config.priority,
        )
    )


__all__ = ["Config", "setup"]
