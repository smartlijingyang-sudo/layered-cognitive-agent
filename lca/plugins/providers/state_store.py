"""State Store Provider plugin — Tier-2."""

from __future__ import annotations

from pydantic import BaseModel, Field

from lca.contracts.protocols import StateStore
from lca.plugins._cordis_adapter import plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["memory"])


@plugin(
    name="lca-state-store-provider",
    requires=["state_store"],
    implements=[StateStore],
    layer="provider",
    side_effects="none",
    policy_class="control",
    description="Register StateStore providers on the StateStoreService Definition.",
    test_suite="tests/test_plugin_tree_single_owner.py",
)
async def setup(ctx, config: Config) -> None:
    from lca.layer0_infra.state_store.in_memory_store import InMemoryStateStore

    if "memory" in config.providers:
        ctx.inject("state_store").register("memory", InMemoryStateStore)
