"""Transport service plugin — provides the ``transport`` capability seam."""

from typing import Any

from lca.contracts.harness.plugin import PluginKind, PluginManifest

manifest = PluginManifest(
    id="lca.transport.service",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.SERVICE,
    provides=("transport",),
)

name = "lca.transport.service"
provides = "transport"


def apply(ctx: Any, config: Any) -> None:
    from lca.layer0_infra.capability.transport import TransportService
    from lca.layer0_infra.transport.a2a_transport import A2ATransport
    from lca.layer0_infra.transport.agent_transport import InternalTransport
    from lca.layer0_infra.transport.mcp_transport import MCPTransport

    service = TransportService()
    for provider in (InternalTransport(), A2ATransport(), MCPTransport()):
        service.register(provider)
    ctx.mount("transport", service)
