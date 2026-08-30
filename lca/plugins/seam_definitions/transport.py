"""Transport Service Definition plugin — Tier-1."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols.infra import TransportRegistryProtocol
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


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
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.capability.transport import TransportService

    ctx.provide("transport", TransportService())
