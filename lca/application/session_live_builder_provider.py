"""Default Provider for Profile-selected Session Live Agent construction."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.harness.collaboration.agent import SessionLiveBuilder
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.application.harness_bridge import build_live_agent


class Config(BaseModel):
    """Default Session Live Agent builder provider configuration."""

    model_config = {"extra": "forbid"}


@plugin(
    id="lca-session-live-builder-provider",
    requires=["agent_loop"],
    provides=["session_live_builder"],
    implements=[SessionLiveBuilder],
    layer="L4",
    effects="none",
    kind=PluginKind.PROVIDER,
    description="Provide the Profile-resolved Session Live Agent construction bridge.",
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Register the default bridge from durable Session facts to a live agent."""

    del config
    ctx.provide("session_live_builder", build_live_agent)


__all__ = ["Config", "setup"]
