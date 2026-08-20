"""Transport Provider plugin — Tier-2 (Internal / A2A / MCP)."""

from __future__ import annotations
from pydantic import BaseModel, Field
from lca.contracts.protocols.infra import AgentTransport
from lca.harness.plugin_api import plugin, PluginKind


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["internal", "a2a", "mcp"])


@plugin(
    id="lca-transport-provider",
    requires=["transport"],
    implements=[AgentTransport],
    layer="L0",
    effects="none",
    description="Register AgentTransport providers on the TransportService Definition.",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PROVIDER,
)
async def setup(ctx, config: Config) -> None:
    from lca.layer0_infra.transport.a2a_transport import A2ATransport
    from lca.layer0_infra.transport.agent_transport import InternalTransport
    from lca.layer0_infra.transport.mcp_transport import MCPTransport

    service = ctx.inject("transport")
    if "internal" in config.providers:
        service.register(InternalTransport())
    if "a2a" in config.providers:
        service.register(A2ATransport())
    if "mcp" in config.providers:
        service.register(MCPTransport())
