"""L0 基础设施协议 —— LLM / Tool / StateStore / Transport / Observability。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from lca.contracts.decision import AgentCard, Observation
from lca.contracts.observability import TraceSpan
from lca.contracts.role_team import CacheConfig, RetryPolicy
from lca.contracts.state import AgentState


@runtime_checkable
class LLMAdapter(Protocol):
    """LLM 适配器接口：屏蔽 provider 差异。"""

    async def complete(self, prompt: str, **kwargs: Any) -> str: ...
    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        """流式输出，逐 chunk 返回文本。子类按需覆写。"""
        ...
        yield ""  # pragma: no cover


@runtime_checkable
class Tool(Protocol):
    """工具能力接口：名称 + 幂等标志 + 执行 + 可选校验。"""

    name: str
    is_idempotent: bool
    default_timeout_s: int

    async def execute(self, args: dict[str, Any]) -> Observation: ...

    def validate(self, args: dict[str, Any]) -> str | None:
        """可选前置校验：返回 None 表示合法，返回错误字符串表示非法。"""
        return None  # pragma: no cover


@runtime_checkable
class ToolRegistry(Protocol):
    """工具注册表：按名称注册和查找 Tool。"""

    def register(self, tool: Tool) -> None: ...
    def get(self, name: str) -> Tool | None: ...


@runtime_checkable
class SafeExecutor(Protocol):
    """安全执行器：带重试 + 缓存的工具执行包装。"""

    async def execute(
        self,
        tool: Tool,
        args: dict[str, Any],
        retry_policy: RetryPolicy,
        cache_config: CacheConfig,
    ) -> Observation: ...


@runtime_checkable
class StateStore(Protocol):
    """状态持久化：save / load AgentState。"""

    async def save(self, state: AgentState) -> str: ...
    async def load(self, state_ref: str) -> AgentState: ...


@runtime_checkable
class AgentTransport(Protocol):
    """Agent 间通信传输抽象：send → poll → receive。"""

    protocol_name: str

    async def send_task(
        self, agent_card: AgentCard | str, subtask: str, context_refs: list[str]
    ) -> str: ...
    async def poll_status(self, task_id: str) -> str: ...
    async def receive_result(self, task_id: str) -> Observation: ...

    async def wait_result(self, task_id: str, timeout_s: float | None = None) -> Observation:
        """等待任务完成并返回结果。

        默认实现可用 poll 循环；进程内传输应覆写为 Future/Event。
        协议层声明此方法以便结构性检查；旧适配器可用 ``hasattr`` 兼容。
        """
        ...


@runtime_checkable
class TransportRegistryProtocol(Protocol):
    """传输注册表接口：按 protocol_name 路由 AgentTransport 实现。"""

    def register(self, transport: AgentTransport) -> None: ...

    def resolve(self, protocol_name: str) -> AgentTransport: ...

    def list_protocols(self) -> list[str]: ...


@runtime_checkable
class Observability(Protocol):
    """可观测性后端：接收 TraceSpan 并输出。"""

    def emit_span(self, span: TraceSpan) -> None: ...
