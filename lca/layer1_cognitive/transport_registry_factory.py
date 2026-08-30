"""Transport registry 的认知层适配工厂。"""

from __future__ import annotations

from lca.contracts.protocols import AgentTransport, TransportRegistryProtocol
from lca.layer0_infra.transport.transport_registry import TransportRegistry


def build_transport_registry(transport: AgentTransport | None = None) -> TransportRegistryProtocol:
    """创建 registry，并可选注册单个显式 transport。"""
    registry = TransportRegistry()
    if transport is not None:
        registry.register(transport)
    return registry


__all__ = ["build_transport_registry"]
