"""Search Service Definition plugin — Tier-1."""

from __future__ import annotations
from typing import Any
from lca.harness.plugin_api import plugin, PluginKind


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
async def setup(ctx: Any, config: Any) -> None:
    from lca.layer0_infra.capability.search import SearchService

    ctx.provide("search", SearchService())
