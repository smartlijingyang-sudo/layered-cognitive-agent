"""State store Service Definition plugin — Tier-1."""

from __future__ import annotations
from typing import Any
from lca.contracts.protocols import StateStore
from lca.harness.plugin_api import plugin, PluginKind


@plugin(
    id="lca-state-store-service",
    provides=["state_store"],
    implements=[StateStore],
    layer="L0",
    effects="none",
    description="Provide the StateStore Definition service (ProviderDispatch + factory table).",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
    kind=PluginKind.SEAM,
)
async def setup(ctx: Any, config: Any) -> None:
    from lca.layer0_infra.capability.state_store import StateStoreService

    ctx.provide("state_store", StateStoreService())
