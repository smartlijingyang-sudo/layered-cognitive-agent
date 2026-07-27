"""第5.11节：所有核心 Protocol 接口定义。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import (
    Any,
    Protocol,
    runtime_checkable,
)

from lca.contracts.decision import Observation, Reflection, StructuredDecision
from lca.contracts.result import Result
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
class ToolProtocol(Protocol):
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


@runtime_checkable
class Body(Protocol):
    async def act(self, decision: StructuredDecision, state: TypedState) -> Observation: ...


@runtime_checkable
class MemorySystem(Protocol):
    async def perceive_and_retrieve(self, state: TypedState) -> TypedState: ...
    async def update_multi_level(
        self, state: TypedState, observation: Observation, reflection: Reflection
    ) -> None: ...


@runtime_checkable
class EventBus(Protocol):
    def emit(self, event_name: str, payload: Any, trace_id: str) -> None: ...
    def subscribe(self, event_name: str, handler: Callable[[Any], Awaitable[None]]) -> None: ...


@runtime_checkable
class PromptManager(Protocol):
    def render(self, template_name: str, variables: dict[str, Any]) -> str: ...
    def register_template(self, name: str, template: str, version: str = "1.0") -> None: ...


@runtime_checkable
class ToolRegistryP(Protocol):
    def register(self, tool: ToolProtocol) -> None: ...
    def get(self, name: str) -> ToolProtocol | None: ...


@runtime_checkable
class SafeExecutorProtocol(Protocol):
    async def execute(
        self,
        tool: ToolProtocol,
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
class HookRegistryP(Protocol):
    def register(self, event_name: str, hook: Hook) -> None: ...
    async def trigger(self, event_name: str, state: TypedState, **kwargs: Any) -> Any: ...


@runtime_checkable
class AgentTransport(Protocol):
    async def send_task(self, agent_card: Any, subtask: str, context_refs: list[str]) -> str: ...
    async def poll_status(self, task_id: str) -> str: ...
    async def receive_result(self, task_id: str) -> Observation: ...


@runtime_checkable
class Observability(Protocol):
    def emit_span(self, span: Any) -> None: ...


@runtime_checkable
class Runtime(Protocol):
    async def run(self, task: str, max_steps: int) -> Result: ...


@runtime_checkable
class AgentProtocol(Protocol):
    async def execute(self, task: str) -> Result: ...
