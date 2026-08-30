"""Search Provider plugin — Tier-2."""

from __future__ import annotations

from pydantic import BaseModel, Field

from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["tavily"])


@plugin(
    id="lca-search-provider",
    requires=["search"],
    layer="L0",
    effects="tools",
    description="Register Search provider functions on the SearchService Definition.",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PROVIDER,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer0_infra.search.providers.tavily import search_tavily

    if "tavily" in config.providers:
        ctx.require("search").register("tavily", search_tavily)
