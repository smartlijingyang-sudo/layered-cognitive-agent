"""TransportRegistry —— 按 protocol_name 路由 AgentTransport 实现。"""

from __future__ import annotations

from lca.contracts.decision import AgentCard, Observation
from lca.contracts.protocols import AgentTransport
from lca.layer0_infra.component_registry import NamedRegistry, RegistryKeyError


class TransportNotFoundError(RegistryKeyError):
    """TransportRegistry 中找不到指定 protocol 的传输实现。"""

    def __init__(self, protocol: str, available: list[str]) -> None:
        self.protocol = protocol
        super().__init__(protocol, "传输协议", available)


class TransportRegistry(NamedRegistry[AgentTransport]):
    """按 protocol_name 注册和解析 AgentTransport 实现。

    注册时校验 key 与实现自报的 protocol_name 一致，
    杜绝"注册表写的是 a2a，塞进去的其实是别的实现"这种手滑。
    """

    _REGISTRY_KIND = "传输协议"

    # 收窄参数：接受 AgentTransport 而非基类的 (name, impl) 对
    def register(self, transport: AgentTransport) -> None:  # type: ignore[override]
        """注册一个 AgentTransport，key 取自 transport.protocol_name。"""
        self._entries[transport.protocol_name] = transport

    def register_as(self, protocol_name: str, transport: AgentTransport) -> None:
        """显式指定 key 注册，校验 key 与 transport.protocol_name 一致。"""
        if transport.protocol_name != protocol_name:
            raise ValueError(
                f"protocol_name 不匹配: 注册 key={protocol_name!r}, "
                f"但 transport 自报 protocol_name={transport.protocol_name!r}"
            )
        self._entries[protocol_name] = transport

    def resolve(self, protocol: str) -> AgentTransport:
        """按 protocol 名解析传输实现，找不到抛 TransportNotFoundError。"""
        try:
            return super().resolve(protocol)
        except RegistryKeyError as exc:
            raise TransportNotFoundError(exc.key, exc.available) from None

    def list_protocols(self) -> list[str]:
        return self.list()


class UnimplementedTransport(AgentTransport):
    """占位传输实现，所有方法抛 NotImplementedError。

    用于在 TransportRegistry 中注册尚未实现的协议（如 a2a/mcp），
    使得路由能到达这里并给出明确报错，而不是静默降级。
    """

    def __init__(self, protocol_name: str, tracking_issue: str = "") -> None:
        self.protocol_name = protocol_name
        self._tracking_issue = tracking_issue

    @property
    def _error_message(self) -> str:
        msg = f"协议 {self.protocol_name!r} 的传输实现尚未完成"
        if self._tracking_issue:
            msg += f" (tracked in {self._tracking_issue})"
        return msg

    async def send_task(
        self, agent_card: AgentCard | str, subtask: str, context_refs: list[str]
    ) -> str:
        raise NotImplementedError(self._error_message)

    async def poll_status(self, task_id: str) -> str:
        raise NotImplementedError(self._error_message)

    async def receive_result(self, task_id: str) -> Observation:
        raise NotImplementedError(self._error_message)

    async def wait_result(self, task_id: str, timeout_s: float | None = None) -> Observation:
        raise NotImplementedError(self._error_message)
