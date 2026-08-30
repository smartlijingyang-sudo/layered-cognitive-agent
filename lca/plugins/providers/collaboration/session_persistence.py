"""Default Provider for the profile-selected durable Session fact stream."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols.session.session_persistence import SessionPersistenceFactory
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.harness.session.persistence import JsonlSessionPersistenceFactory


class Config(BaseModel):
    """Default session-persistence provider configuration."""

    model_config = {"extra": "forbid"}


@plugin(
    id="lca-session-persistence-jsonl-provider",
    requires=[],
    provides=["session_persistence_factory"],
    implements=[SessionPersistenceFactory],
    layer="L0",
    effects="filesystem",
    kind=PluginKind.PROVIDER,
    description="Provide JSONL persistence for durable Session fact streams.",
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Register the default Session persistence factory."""

    del config
    ctx.provide("session_persistence_factory", JsonlSessionPersistenceFactory())


__all__ = ["Config", "setup"]
