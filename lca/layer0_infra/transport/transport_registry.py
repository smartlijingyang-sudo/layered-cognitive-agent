"""TransportRegistry —— 按 protocol_name 路由 AgentTransport 实现。"""

from __future__ import annotations

from lca.contracts.protocols import AgentTransport, TransportRegistryProtocol
from lca.layer0_infra.component_registry import NamedRegistry, RegistryKeyError


class TransportNotFoundError(RegistryKeyError):
    """TransportRegistry 中找不到指定 protocol 的传输实现。"""

    def __init__(self, protocol: str, available: list[str]) -> None:
        self.protocol = protocol
        super().__init__(protocol, "传输协议", available)


class TransportRegistry(NamedRegistry[AgentTransport], TransportRegistryProtocol):
    """按 protocol_name 注册和解析 AgentTransport 实现。

    注册时校验 key 与实现自报的 protocol_name 一致，
    杜绝"注册表写的是 a2a，塞进去的其实是别的实现"这种手滑。
    """

    _REGISTRY_KIND = "传输协议"

    # 收窄参数：接受 AgentTransport 而非基类的 (name, impl) 对
    def register(self, transport: AgentTransport) -> None:  # type: ignore[override]
        """注册一个 AgentTransport，key 取自 transport.protocol_name。

        协议名的所有权由基础发现型注册表统一保护：同一协议的替换
        必须在 Profile 的选择接缝完成，不能依赖 provider 的注册顺序。
        """
        super().register(transport.protocol_name, transport)

    def register_as(self, protocol_name: str, transport: AgentTransport) -> None:
        """显式指定 key 注册，校验 key 与 transport.protocol_name 一致。"""
        if transport.protocol_name != protocol_name:
            raise ValueError(
                f"protocol_name 不匹配: 注册 key={protocol_name!r}, "
                f"但 transport 自报 protocol_name={transport.protocol_name!r}"
            )
        super().register(protocol_name, transport)

    def resolve(self, protocol: str) -> AgentTransport:
        """按 protocol 名解析传输实现，找不到抛 TransportNotFoundError。"""
        try:
            return super().resolve(protocol)
        except RegistryKeyError as exc:
            raise TransportNotFoundError(exc.key, exc.available) from None

    def list_protocols(self) -> list[str]:
        return self.list()
