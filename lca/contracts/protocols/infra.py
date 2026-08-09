"""L0 基础设施协议 —— LLM / Tool / StateStore / Transport。

可观测性协议见 ``lca.contracts.protocols.observability``。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, ClassVar, Protocol, runtime_checkable

from lca.contracts.atoms.enums import LLMStreamEventType
from lca.contracts.models.core.decision import AgentCard, Observation
from lca.contracts.models.core.llm import LLMResponse, LLMStreamEvent
from lca.contracts.models.core.sandbox import (
    MountManifest,
    SandboxExecResult,
    SandboxResult,
    SessionConfig,
    SessionInfo,
)
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.team.role_team import CacheConfig, RetryPolicy


@runtime_checkable
class LLMAdapter(Protocol):
    """LLM 适配器接口：屏蔽 provider 差异。

    ``complete`` 返回结构化 :class:`LLMResponse`（文本 + 模型 + token 用量），
    用量是可观测性成本链路的单一事实源。
    """

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse: ...
    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
        """流式输出，逐事件返回结构化 ``LLMStreamEvent``。子类按需覆写。"""
        ...
        yield LLMStreamEvent(type=LLMStreamEventType.COMPLETED)  # pragma: no cover


@runtime_checkable
class Tool(Protocol):
    """工具能力接口：名称 + 描述 + 参数 schema + 幂等标志 + 执行 + 可选校验。

    ``description`` 和 ``parameters`` 遵循 OpenAI function-calling 规范，
    由 LLM 适配器转换为原生 tool spec 传递给模型，无需在 prompt 中
    手工描述参数格式。
    """

    name: str
    description: str
    parameters: ClassVar[dict[str, Any]]
    is_idempotent: bool
    default_timeout_s: int

    async def execute(self, args: dict[str, Any]) -> Observation: ...

    def validate(self, args: dict[str, Any]) -> str | None:
        """可选前置校验：返回 None 表示合法，返回错误字符串表示非法。"""
        return None  # pragma: no cover


@runtime_checkable
class Sandbox(Protocol):
    """代码沙箱：隔离执行用户/模型生成的代码，可选挂载输入文件。

    支持可选的有状态会话（session）——容器跨调用存活，变量/包/文件系统保持。
    不支持会话的适配器保留默认实现（返回 None），调用方优雅降级为无状态模式。

    ``**kwargs`` 透传扩展元数据（如 ``invocation_id``），镜像
    ``LLMAdapter.stream`` 惯例，避免 Protocol 破坏性扩签。
    执行期 stdout/stderr 增量由具体适配器经 journal ``record`` 发射
    （见 ``SandboxOutputDelta``），本协议只承诺终态 ``SandboxResult``。
    """

    async def run(
        self,
        code: str,
        language: str = "python",
        files: dict[str, bytes] | None = None,
        timeout_s: int = 60,
        **kwargs: Any,
    ) -> SandboxResult: ...

    async def create_session(self, config: SessionConfig | None = None) -> SessionInfo | None:
        """创建有状态会话。不支持时返回 None，调用方降级为无状态 run。"""
        ...

    async def run_in_session(
        self,
        session_id: str,
        code: str,
        language: str = "python",
        timeout_s: int = 60,
        **kwargs: Any,
    ) -> SandboxResult:
        """在已有会话中执行代码。会话状态（变量、包、文件）跨调用保持。"""
        ...

    async def destroy_session(self, session_id: str) -> None:
        """销毁会话并释放资源。幂等——重复调用不报错。"""
        ...


@runtime_checkable
class SandboxRuntime(Protocol):
    """Run-bound sandbox runtime — mount, inspect, execute (ADR-0050)."""

    @property
    def manifest(self) -> MountManifest: ...

    @property
    def inspect_profile(self) -> dict[str, object] | None: ...

    @property
    def environment_ready(self) -> bool: ...

    async def ensure_ready(
        self, explicit_ids: list[str] | None = None
    ) -> SandboxExecResult | None: ...

    async def inspect(self, *, force: bool = False) -> SandboxExecResult: ...

    async def execute(
        self,
        code: str,
        *,
        language: str = "python",
        timeout_s: int | None = None,
        invocation_id: str = "",
        explicit_attachment_ids: list[str] | None = None,
        extra_files: dict[str, bytes] | None = None,
    ) -> SandboxExecResult: ...

    async def destroy(self) -> None: ...


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
