"""Profile-selected composite publisher for declarative Agent Loop lifecycle events.

Individual plugins contribute passive subscribers through a neutral registry.
This provider is the sole producer of the runtime's lifecycle-publisher
capability and freezes contributions during profile boot for runtime locality.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from lca.contracts.capabilities import (
    RUNTIME_LIFECYCLE_PUBLISHER,
    RUNTIME_LIFECYCLE_SUBSCRIBER_REGISTRY,
)
from lca.contracts.protocols.runtime_lifecycle import (
    RuntimeLifecyclePublisher,
    RuntimeLifecycleSubscriberRegistry,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.runtime.runtime_event_publisher import (
    CompositeRuntimeLifecyclePublisher,
    LifecyclePublisherFailureMode,
)


class Config(BaseModel):
    """Configure whether lifecycle-subscriber failures affect the Agent Loop."""

    failure_mode: Literal["fail_open", "fail_closed"] = "fail_open"
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-runtime-lifecycle-publisher",
    Config=Config,
    provides=[RUNTIME_LIFECYCLE_PUBLISHER.key],
    requires=[RUNTIME_LIFECYCLE_SUBSCRIBER_REGISTRY.key],
    implements=[RuntimeLifecyclePublisher],
    layer="L2",
    effects="none",
    description="Freeze passive lifecycle subscribers into the Agent Loop event publisher.",
    test_suite="tests/runtime/test_runtime_lifecycle_plugins.py",
    kind=PluginKind.COMPOSITE,
)
async def setup(ctx: PluginContext, config: BaseModel) -> None:
    """Build one immutable publisher for every runtime assembled from this Profile."""

    if not isinstance(config, Config):
        raise TypeError("runtime lifecycle publisher config must be Config")
    registry = ctx.require(RUNTIME_LIFECYCLE_SUBSCRIBER_REGISTRY)
    if not isinstance(registry, RuntimeLifecycleSubscriberRegistry):
        raise TypeError(
            "runtime_lifecycle_subscriber_registry must implement "
            "RuntimeLifecycleSubscriberRegistry"
        )
    ctx.provide(
        RUNTIME_LIFECYCLE_PUBLISHER.key,
        CompositeRuntimeLifecyclePublisher(
            registry.snapshot(),
            failure_mode=LifecyclePublisherFailureMode(config.failure_mode),
        ),
    )


__all__ = ["Config", "setup"]
