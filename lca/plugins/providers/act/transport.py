"""Transport Provider plugin — Tier-2 (Internal / A2A / MCP)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.runtime.infra import AgentTransport
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


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
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=("plugin.serve",),
        evidence=("lca-transport-provider.checked", "lca-transport-provider.served"),
        revision="v1",
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.transport.a2a_transport import A2ATransport
    from lca.infrastructure.transport.agent_transport import InternalTransport
    from lca.infrastructure.transport.mcp_transport import MCPTransport

    service = ctx.require("transport")
    if "internal" in config.providers:
        service.register(InternalTransport())
    if "a2a" in config.providers:
        service.register(A2ATransport())
    if "mcp" in config.providers:
        service.register(MCPTransport())
