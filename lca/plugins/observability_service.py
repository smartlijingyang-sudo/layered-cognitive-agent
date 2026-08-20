"""Observability Service Definition plugin — Tier-1."""

from __future__ import annotations

from typing import Any

from lca.contracts.protocols import ObservabilityBackend
from lca.plugins._cordis_adapter import plugin


@plugin(
    name="lca-observability-service",
    provides=["observability"],
    implements=[ObservabilityBackend],
    layer="service",
    side_effects="none",
    policy_class="observe",
    description="Provide the Observability Definition service (ProviderDispatch + factory table).",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
)
async def setup(ctx: Any, config: Any) -> None:
    from lca.layer0_infra.capability.observability import ObservabilityService

    ctx.provide("observability", ObservabilityService())
