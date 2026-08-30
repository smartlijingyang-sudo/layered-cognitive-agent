"""transport seam Definition — owns ctx.transport."""

from __future__ import annotations

from lca.contracts.protocols import AgentTransport
from lca.infrastructure.transport.transport_registry import TransportRegistry


class TransportService(TransportRegistry):
    """Service Definition：按 protocol_name 挂载 AgentTransport Provider。"""

    def register_provider(self, transport: AgentTransport) -> None:
        self.register(transport)
