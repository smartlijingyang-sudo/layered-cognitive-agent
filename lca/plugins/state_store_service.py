"""State store Service Definition plugin — Tier-1."""

from __future__ import annotations

from typing import Any

from lca.contracts.protocols import StateStore
from lca.plugins._cordis_adapter import plugin


@plugin(
    name="lca-state-store-service",
    provides=["state_store"],
    implements=[StateStore],
    layer="service",
    side_effects="none",
    policy_class="control",
    description="Provide the StateStore Definition service (ProviderDispatch + factory table).",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
)
async def setup(ctx: Any, config: Any) -> None:
    from lca.layer0_infra.capability.state_store import StateStoreService

    ctx.provide("state_store", StateStoreService())
