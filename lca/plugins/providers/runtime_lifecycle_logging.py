"""Default structured-log contribution for Agent Loop lifecycle events."""

from __future__ import annotations

from pydantic import BaseModel, Field

from lca.contracts.capabilities import RUNTIME_LIFECYCLE_SUBSCRIBER_REGISTRY
from lca.contracts.protocols.runtime_lifecycle import (
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
    test_suite="tests/layer2_runtime/test_runtime_lifecycle_plugins.py",
    kind=PluginKind.PROVIDER,
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
