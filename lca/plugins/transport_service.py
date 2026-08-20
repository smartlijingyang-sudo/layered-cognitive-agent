"""Transport Service Definition plugin — Tier-1."""

from __future__ import annotations
from typing import Any
from lca.contracts.protocols.infra import TransportRegistryProtocol
from lca.harness.plugin_api import plugin, PluginKind


@plugin(
    id="lca-transport-service",
    provides=["transport"],
    implements=[TransportRegistryProtocol],
    layer="L0",
    effects="none",
    description="Provide the Transport Definition service (registry of AgentTransport providers).",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
    kind=PluginKind.SEAM,
)
async def setup(ctx: Any, config: Any) -> None:
    from lca.layer0_infra.capability.transport import TransportService

    ctx.provide("transport", TransportService())
