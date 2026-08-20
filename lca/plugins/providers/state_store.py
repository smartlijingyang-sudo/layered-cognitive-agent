"""State Store Provider plugin — Tier-2."""

from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel, Field


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["memory"])


@plugin(name="lca-state-store-provider", inject=["state_store"])
async def setup(ctx: Context, config: Config) -> None:
    from lca.layer0_infra.state_store.in_memory_store import InMemoryStateStore

    if "memory" in config.providers:
        ctx.inject("state_store").register("memory", InMemoryStateStore)
