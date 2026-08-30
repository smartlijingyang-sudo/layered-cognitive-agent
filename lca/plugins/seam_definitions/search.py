"""Search Service Definition plugin — Tier-1."""

from __future__ import annotations

from pydantic import BaseModel

from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-search-service",
    provides=["search"],
    implements=[],
    layer="L0",
    effects="tools",
    description="Provide the Search Definition service (ProviderDispatch + search fn table).",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
    kind=PluginKind.SEAM,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer0_infra.capability.search import SearchService

    ctx.provide("search", SearchService())
