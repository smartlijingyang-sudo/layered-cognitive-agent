"""L0 基础设施协议 —— LLM / Tool / StateStore / Transport / Observability。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from lca.contracts.decision import AgentCard, Observation
from lca.contracts.observability import TraceSpan
from lca.contracts.role_team import CacheConfig, RetryPolicy
from lca.contracts.state import TypedState


@runtime_checkable
class LLMAdapter(Protocol):
    async def complete(self, prompt: str, **kwargs: Any) -> str: ...
    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        """流式输出，逐 chunk 返回文本。子类按需覆写。"""
        ...
        yield ""  # pragma: no cover


@runtime_checkable
class Tool(Protocol):
    name: str
    is_idempotent: bool
    default_timeout_s: int

    async def execute(self, args: dict[str, Any]) -> Observation: ...

    def validate(self, args: dict[str, Any]) -> str | None:
        """可选前置校验：返回 None 表示合法，返回错误字符串表示非法。"""
        return None  # pragma: no cover


@runtime_checkable
class ToolRegistry(Protocol):
    def register(self, tool: Tool) -> None: ...
    def get(self, name: str) -> Tool | None: ...


@runtime_checkable
class SafeExecutor(Protocol):
    async def execute(
        self,
        tool: Tool,
        args: dict[str, Any],
        retry_policy: RetryPolicy,
        cache_config: CacheConfig,
    ) -> Observation: ...


@runtime_checkable
class StateStore(Protocol):
    async def save(self, state: TypedState) -> str: ...
    async def load(self, state_ref: str) -> TypedState: ...


@runtime_checkable
class AgentTransport(Protocol):
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
    def emit_span(self, span: TraceSpan) -> None: ...
