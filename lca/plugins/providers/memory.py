"""Memory Provider plugin — Tier-2."""

from __future__ import annotations

from pydantic import BaseModel, Field

from lca.contracts.protocols import MemorySystem
from lca.plugins._cordis_adapter import plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["simple"])


@plugin(
    name="lca-memory-provider",
    requires=["memory"],
    implements=[MemorySystem],
    layer="provider",
    side_effects="memory",
    policy_class="control",
    description="Register MemorySystem providers on the MemoryService Definition.",
    test_suite="tests/test_plugin_tree_single_owner.py",
)
async def setup(ctx, config: Config) -> None:
    from lca.layer1_cognitive.memory.simple_memory import SimpleMemorySystem

    if "simple" in config.providers:
        ctx.inject("memory").register("simple", SimpleMemorySystem)
