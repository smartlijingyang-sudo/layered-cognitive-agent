"""工具执行管线契约 —— 五阶段可拦截管线。

pre-execute → guards → execute
→ post-execute → result 管线。将"工具执行"从一步调用展开为五阶段管线，
每个阶段都是可插拔的拦截点。

五阶段：
    1. **pre-execute**：权限/审批/sandbox 策略。决定 allow | deny | ask。
    2. **monotonic guards**：只 deny 或 abstain，不能把 deny 翻回 allow。
       监听器顺序不影响结果（单调性保证）。
    3. **execute**：around-dispatch——timeout/retry/metrics 包装 tool body。
    4. **post-execute**：结果改写——accept | block | replace。
    5. **finalize**：纯函数最终变换（日志截断/脱敏等），不可抛异常。

关键不变量：
- 单调守卫只能 deny 或 abstain——第一个 deny 赢，顺序无关。
- around-dispatch 的 signal 融合保证调用方取消传播不被切断。
- finalize 纯函数，异常只记日志不传播。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# ── 决策类型 ─────────────────────────────────────────────


@dataclass(frozen=True)
class ToolPreDecision:
    """pre-execute 阶段决策。"""

    kind: str  # "allow" | "deny" | "ask"
    reason: str = ""


@dataclass(frozen=True)
class ToolPostDecision:
    """post-execute 阶段决策。"""

    kind: str  # "accept" | "block"
    content: Any = None  # 替换内容（accept 时）或反馈（block 时）


@dataclass(frozen=True)
class ToolDefinition:
    """Provider-independent tool declaration exposed to a model and UI."""

    name: str
    description: str
    parameters: dict[str, Any]
    result_schema: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"
    is_idempotent: bool = False
    default_timeout_ms: int = 30_000


# ── 执行上下文 ───────────────────────────────────────────


@dataclass(frozen=True)
class ToolExecutionContext:
    """工具执行的不可变身份。"""

    tool_name: str
    args: dict[str, Any]
    invocation_id: str = ""
    agent_role: str = ""
    definition: ToolDefinition | None = None
    provider_id: str = ""


@dataclass(frozen=True)
class ToolExecutionResult:
    """工具执行结果（成功或失败）。"""

    ok: bool
    output: Any = None
    error: str = ""
    latency_ms: int = 0


# ── 管线阶段回调类型 ────────────────────────────────────

PreExecuteFn = Callable[[ToolExecutionContext], Awaitable[ToolPreDecision]]
GuardFn = Callable[[ToolExecutionContext], str | None]
ExecuteFn = Callable[[ToolExecutionContext], Awaitable[ToolExecutionResult]]
ExecuteNextFn = Callable[[ToolExecutionContext], Awaitable[ToolExecutionResult]]
ExecuteMiddlewareFn = Callable[
    [ToolExecutionContext, ExecuteNextFn], Awaitable[ToolExecutionResult]
]
PostExecuteFn = Callable[[ToolExecutionContext, ToolExecutionResult], Awaitable[ToolPostDecision]]
FinalizeFn = Callable[[ToolExecutionResult], ToolExecutionResult]


@runtime_checkable
class ToolProvider(Protocol):
    """Binds a definition to one concrete execution environment."""

    provider_id: str

    async def execute(self, ctx: ToolExecutionContext) -> ToolExecutionResult: ...


@runtime_checkable
class ToolRenderer(Protocol):
    """Renders a definition without observing its concrete provider."""

    def render(self, definition: ToolDefinition) -> Any: ...


# ── 管线协议 ─────────────────────────────────────────────


@runtime_checkable
class ToolExecutionPipeline(Protocol):
    """五阶段工具执行管线。

    Body / SafeExecutor 调用 ``run(ctx)`` 即走完整管线。
    各阶段通过 ``add_pre_execute`` / ``add_guard`` 等方法注册拦截器。
    """

    async def run(self, ctx: ToolExecutionContext) -> ToolExecutionResult:
        """走完整管线：pre → guards → execute → post → finalize。"""
        ...

    def set_executor(self, executor: ExecuteFn) -> None:
        """设置核心执行函数（tool body）。"""
        ...

    def register_tool(self, definition: ToolDefinition, provider: ToolProvider) -> None:
        """Register one definition and its active provider binding."""
        ...

    def register_provider(self, tool_name: str, provider: ToolProvider) -> None:
        """Replace the provider binding while retaining the definition."""
        ...

    def set_renderer(self, renderer: ToolRenderer) -> None:
        """Configure the provider-independent model/UI renderer."""
        ...

    def render(self, tool_name: str) -> Any:
        """Render one registered definition."""
        ...

    async def execute(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        invocation_id: str = "",
        agent_role: str = "",
    ) -> ToolExecutionResult:
        """Execute a registered provider through the complete policy pipeline."""
        ...

    def add_pre_execute(self, fn: PreExecuteFn) -> None:
        """注册 pre-execute 拦截器（可叠加，按注册顺序执行）。"""
        ...

    def add_guard(self, fn: GuardFn) -> None:
        """注册单调守卫（只 deny 或 abstain，第一个 deny 赢）。"""
        ...

    def add_approval_policy(self, fn: PreExecuteFn) -> None:
        """Register an approval policy at ``tools.pre_execute``."""
        ...

    def add_sandbox_guard(self, fn: GuardFn) -> None:
        """Register a sandbox guard at ``tools.pre_execute``."""
        ...

    def add_execute(self, fn: ExecuteMiddlewareFn) -> None:
        """Register around-dispatch middleware at ``tools.execute``."""
        ...

    def add_post_execute(self, fn: PostExecuteFn) -> None:
        """注册 post-execute 结果改写器。"""
        ...

    def add_finalize(self, fn: FinalizeFn) -> None:
        """注册 finalize 纯函数变换（异常隔离）。"""
        ...
