"""State Store Provider plugin — Tier-2."""

from __future__ import annotations
from pydantic import BaseModel, Field
from lca.contracts.protocols import StateStore
from lca.harness.plugin_api import plugin, PluginKind


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["memory"])


@plugin(
    id="lca-state-store-provider",
    requires=["state_store"],
    implements=[StateStore],
    layer="L0",
    effects="none",
    description="Register StateStore providers on the StateStoreService Definition.",
    test_suite="tests/test_plugin_tree_single_owner.py",
    kind=PluginKind.PROVIDER,
)
async def setup(ctx, config: Config) -> None:
    from lca.layer0_infra.state_store.in_memory_store import InMemoryStateStore

    if "memory" in config.providers:
        ctx.inject("state_store").register("memory", InMemoryStateStore)
