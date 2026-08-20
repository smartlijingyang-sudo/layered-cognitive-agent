"""Search Service Definition plugin — Tier-1."""

from __future__ import annotations

from typing import Any

from lca.plugins._cordis_adapter import plugin


@plugin(
    name="lca-search-service",
    provides=["search"],
    implements=[],
    layer="service",
    side_effects="tools",
    policy_class="control",
    description="Provide the Search Definition service (ProviderDispatch + search fn table).",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
)
async def setup(ctx: Any, config: Any) -> None:
    from lca.layer0_infra.capability.search import SearchService

    ctx.provide("search", SearchService())
