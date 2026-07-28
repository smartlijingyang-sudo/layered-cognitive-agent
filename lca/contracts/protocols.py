"""第5.11节：所有核心 Protocol 接口定义。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import (
    Any,
    Protocol,
    runtime_checkable,
)

from lca.contracts.decision import Observation, Reflection, StructuredDecision
from lca.contracts.memory import MemoryRecord
from lca.contracts.result import Result
from lca.contracts.role_team import CacheConfig, RetryPolicy, TeamConfig
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


@runtime_checkable
class Reasoner(Protocol):
    async def generate_candidates(self, state: TypedState, n: int = 1) -> list[str]: ...


@runtime_checkable
class DecisionParser(Protocol):
    def parse(self, raw_output: str, state: TypedState) -> StructuredDecision: ...


@runtime_checkable
class Critic(Protocol):
    async def critique(self, state: TypedState, observation: Observation) -> Reflection: ...


@runtime_checkable
class TaskDecomposer(Protocol):
    async def decompose(self, state: TypedState) -> list[str]: ...


@runtime_checkable
class StatePredictor(Protocol):
    async def predict(self, state: TypedState, candidate_action: str) -> dict[str, Any]: ...


@runtime_checkable
class StateEvaluator(Protocol):
    async def score(self, state: TypedState, predicted_state: dict[str, Any]) -> float: ...


@runtime_checkable
class ConflictMonitor(Protocol):
    async def check(self, state: TypedState, candidates: list[StructuredDecision]) -> list[str]: ...


@runtime_checkable
class TaskCoordinator(Protocol):
    async def arbitrate(
        self,
        state: TypedState,
        candidates: list[StructuredDecision],
        scores: list[float],
    ) -> StructuredDecision: ...


@runtime_checkable
class BrainStrategy(Protocol):
    async def think(self, state: TypedState) -> StructuredDecision: ...
    async def reflect(self, state: TypedState, observation: Observation) -> Reflection: ...
    def set_team_roster(self, roster_desc: str) -> None: ...


@runtime_checkable
class Body(Protocol):
    async def act(self, decision: StructuredDecision, state: TypedState) -> Observation: ...
    def bind_transport(self, transport: AgentTransport) -> None: ...


@runtime_checkable
class MemorySystem(Protocol):
    async def perceive_and_retrieve(self, state: TypedState) -> TypedState: ...
    async def update_multi_level(
        self, state: TypedState, observation: Observation, reflection: Reflection
    ) -> None: ...


@runtime_checkable
class SharedMemoryStore(Protocol):
    """跨 Agent 共享记忆存储接口。

    按 layer 分流读写，由 TeamOrchestrator 构造并注入各 MemorySystem 实例。
    """

    def is_shared(self, layer: str) -> bool: ...
    def add_record(self, layer: str, record: MemoryRecord) -> None: ...
    def get_records(self, layer: str) -> list[MemoryRecord]: ...


@runtime_checkable
class EventBus(Protocol):
    def emit(self, event_name: str, payload: Any, trace_id: str) -> None: ...
    def subscribe(self, event_name: str, handler: Callable[[Any], Awaitable[None]]) -> None: ...


@runtime_checkable
class PromptManager(Protocol):
    def render(self, template_name: str, variables: dict[str, Any]) -> str: ...
    def register_template(self, name: str, template: str, version: str = "1.0") -> None: ...


@runtime_checkable
class SkillRouter(Protocol):
    """运行时动态选择 Prompt 模板 / 工具子集。

    挂在 BrainStrategy.think 前置钩子，根据当前 state 决定用哪个 template。
    默认实现 KeywordSkillRouter（关键词匹配，零成本），
    可选 LLMSkillRouter（小模型分类）。
    """

    async def route(self, state: TypedState) -> str: ...


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
class Hook(Protocol):
    async def __call__(self, event_name: str, state: TypedState, **kwargs: Any) -> None: ...


@runtime_checkable
class HookRegistry(Protocol):
    def register(self, event_name: str, hook: Hook) -> None: ...
    async def trigger(self, event_name: str, state: TypedState, **kwargs: Any) -> Any: ...


@runtime_checkable
class AgentTransport(Protocol):
    protocol_name: str

    async def send_task(self, agent_card: Any, subtask: str, context_refs: list[str]) -> str: ...
    async def poll_status(self, task_id: str) -> str: ...
    async def receive_result(self, task_id: str) -> Observation: ...


@runtime_checkable
class Observability(Protocol):
    def emit_span(self, span: Any) -> None: ...


@runtime_checkable
class Runtime(Protocol):
    async def run(
        self,
        task: str,
        max_steps: int,
        max_wall_clock_seconds: int | None = None,
        **context: str,
    ) -> Result: ...
    def configure(self, **capabilities: Any) -> None: ...


@runtime_checkable
class AgentRuntime(Protocol):
    async def execute(self, task: str, **context: str) -> Result: ...


@runtime_checkable
class TeamRuntime(Protocol):
    """团队级入口契约：接收 objective，跑完编排后返回 Result。

    区别于 AgentRuntime.execute：语义单位是"团队"而非单个 Agent，
    不携带 max_steps（预算下沉到各 BaseAgent 自身）。
    """

    async def run(self, objective: str) -> Result: ...


@dataclass
class OrchestrationContext:
    """编排策略的运行时上下文，由 TeamOrchestrator 构造并传给策略实例。"""

    members: list[Any] = field(default_factory=list)
    config: TeamConfig | None = None
    supervisor: Any | None = None
    transport: AgentTransport | None = None
    roster_desc: str = ""


@runtime_checkable
class OrchestrationStrategy(Protocol):
    """编排策略接口：每种 process 模式对应一个实现。"""

    async def run(self, context: OrchestrationContext, objective: str) -> Result: ...


@runtime_checkable
class CompletionPolicy(Protocol):
    """确定性收尾策略：校验候选决策是否可被采纳。

    与 TaskCoordinator 平级，但职责不同：
    TaskCoordinator 在多候选间仲裁，CompletionPolicy 对仲裁结果做 guardrail。
    """

    async def enforce(
        self,
        state: TypedState,
        decision: StructuredDecision,
    ) -> StructuredDecision: ...


@runtime_checkable
class Synthesizer(Protocol):
    """MoA 聚合器：将多个并行候选结果合成为一个最终结果。

    用于 ParallelStrategy 的 fan-in 阶段。不同实现对应不同聚合策略：
    - ConcatSynthesizer: 简单拼接所有候选输出
    - LLMSynthesizer: 调用 LLM 做 Layer-2 提炼（MoA 核心）
    - BestOfSynthesizer: 复用 TaskCoordinator.arbitrate 选优
    """

    async def synthesize(self, objective: str, candidates: list[Result]) -> Result: ...


@runtime_checkable
class RegistryProtocol(Protocol):
    """按名称注册和解析实体的通用注册表接口。

    具体实现（如 NamedRegistry）提供泛型基类继承，
    消费方依赖此 Protocol 进行跨层解耦。
    """

    def register(self, name: str, impl: Any) -> None: ...

    def resolve(self, name: str) -> Any: ...

    def list(self) -> list[str]: ...

    def __contains__(self, name: str) -> bool: ...


@runtime_checkable
class TransportRegistryProtocol(Protocol):
    """传输注册表接口：按 protocol_name 路由 AgentTransport 实现。

    具体实现（如 TransportRegistry）在 layer0 提供，
    layer1 Body 和 ActionHandler 依赖此 Protocol 进行解耦。
    """

    def register(self, transport: AgentTransport) -> None: ...

    def resolve(self, protocol_name: str) -> AgentTransport: ...

    def list_protocols(self) -> list[str]: ...
