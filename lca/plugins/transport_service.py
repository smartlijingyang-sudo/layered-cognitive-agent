"""Transport Service Definition plugin — Tier-1."""

from __future__ import annotations

from typing import Any

from lca.contracts.protocols.infra import TransportRegistryProtocol
from lca.plugins._cordis_adapter import plugin


@plugin(
    name="lca-transport-service",
    provides=["transport"],
    implements=[TransportRegistryProtocol],
    layer="service",
    side_effects="none",
    policy_class="control",
    description="Provide the Transport Definition service (registry of AgentTransport providers).",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
)
async def setup(ctx: Any, config: Any) -> None:
    from lca.layer0_infra.capability.transport import TransportService

    ctx.provide("transport", TransportService())
