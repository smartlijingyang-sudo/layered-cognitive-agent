"""Search Provider plugin — Tier-2."""

from __future__ import annotations

from pydantic import BaseModel, Field

from lca.plugins._cordis_adapter import plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["tavily"])


@plugin(
    name="lca-search-provider",
    requires=["search"],
    layer="provider",
    side_effects="tools",
    policy_class="control",
    description="Register Search provider functions on the SearchService Definition.",
    test_suite="tests/test_plugin_alignment.py",
)
async def setup(ctx, config: Config) -> None:
    from lca.layer0_infra.search.providers.tavily import search_tavily

    if "tavily" in config.providers:
        ctx.inject("search").register("tavily", search_tavily)
