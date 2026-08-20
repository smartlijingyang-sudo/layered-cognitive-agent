"""Search Provider plugin — Tier-2."""
from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel, Field


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["tavily"])


@plugin(name="lca-search-provider", inject=["search"])
async def setup(ctx: Context, config: Config) -> None:
    from lca.layer0_infra.search.providers.tavily import search_tavily

    if "tavily" in config.providers:
        ctx.inject("search").register("tavily", search_tavily)
