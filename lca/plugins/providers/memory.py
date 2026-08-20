"""Memory Provider plugin — Tier-2."""
from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel, Field


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["simple"])


@plugin(name="lca-memory-provider", inject=["memory"])
async def setup(ctx: Context, config: Config) -> None:
    from lca.layer1_cognitive.memory.simple_memory import SimpleMemorySystem

    if "simple" in config.providers:
        ctx.inject("memory").register("simple", SimpleMemorySystem)
