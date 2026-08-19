"""Transport Provider plugin — Tier-2 (Internal / A2A / MCP)."""
from __future__ import annotations

from cordis import plugin
from pydantic import BaseModel, Field


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["internal", "a2a", "mcp"])


@plugin(name="lca-transport-provider", inject=["transport"])
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
