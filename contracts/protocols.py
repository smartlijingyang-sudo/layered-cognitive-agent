"""第5.11节：所有核心 Protocol 接口定义。"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional, Protocol

from contracts.state import TypedState
from contracts.decision import StructuredDecision, Observation, Reflection
from contracts.role_team import RetryPolicy, CacheConfig


class LLMAdapter(Protocol):
    async def complete(self, prompt: str, **kwargs: Any) -> str: ...


class ToolProtocol(Protocol):
    name: str
    is_idempotent: bool
    default_timeout_s: int

    async def execute(self, args: dict[str, Any]) -> Observation: ...


class Reasoner(Protocol):
    async def generate_candidates(self, state: TypedState, n: int = 1) -> list[str]: ...


class DecisionParser(Protocol):
    def parse(self, raw_output: str, state: TypedState) -> StructuredDecision: ...


class Critic(Protocol):
    async def critique(self, state: TypedState, observation: Observation) -> Reflection: ...


class TaskDecomposer(Protocol):
    async def decompose(self, state: TypedState) -> list[str]: ...


class StatePredictor(Protocol):
    async def predict(self, state: TypedState, candidate_action: str) -> dict[str, Any]: ...


class StateEvaluator(Protocol):
    async def score(self, state: TypedState, predicted_state: dict[str, Any]) -> float: ...


class ConflictMonitor(Protocol):
    async def check(self, state: TypedState, candidates: list[StructuredDecision]) -> list[str]: ...


class TaskCoordinator(Protocol):
    async def arbitrate(
        self, state: TypedState, candidates: list[StructuredDecision], scores: list[float]
    ) -> StructuredDecision: ...


class BrainStrategy(Protocol):
    async def think(self, state: TypedState) -> StructuredDecision: ...
    async def reflect(self, state: TypedState, observation: Observation) -> Reflection: ...


class Body(Protocol):
    async def act(self, decision: StructuredDecision, state: TypedState) -> Observation: ...


class MemorySystem(Protocol):
    async def perceive_and_retrieve(self, state: TypedState) -> TypedState: ...
    async def update_multi_level(
        self, state: TypedState, observation: Observation, reflection: Reflection
    ) -> None: ...


class EventBus(Protocol):
    def emit(self, event_name: str, payload: Any, trace_id: str) -> None: ...
    def subscribe(self, event_name: str, handler: Callable[[Any], Awaitable[None]]) -> None: ...


class PromptManager(Protocol):
    def render(self, template_name: str, variables: dict[str, Any]) -> str: ...
    def register_template(self, name: str, template: str, version: str = "1.0") -> None: ...


class ToolRegistryP(Protocol):
    def register(self, tool: ToolProtocol) -> None: ...
    def get(self, name: str) -> Optional[ToolProtocol]: ...


class SafeExecutorProtocol(Protocol):
    async def execute(
        self, tool: ToolProtocol, args: dict[str, Any], retry_policy: RetryPolicy, cache_config: CacheConfig
    ) -> Observation: ...


class StateStore(Protocol):
    async def save(self, state: TypedState) -> str: ...
    async def load(self, state_ref: str) -> TypedState: ...


class Hook(Protocol):
    async def __call__(self, event_name: str, state: TypedState, **kwargs: Any) -> None: ...


class HookRegistryP(Protocol):
    def register(self, event_name: str, hook: Hook) -> None: ...
    async def trigger(self, event_name: str, state: TypedState, **kwargs: Any) -> Any: ...


class AgentTransport(Protocol):
    async def send_task(self, agent_card: Any, subtask: str, context_refs: list[str]) -> str: ...
    async def poll_status(self, task_id: str) -> str: ...
    async def receive_result(self, task_id: str) -> Observation: ...
