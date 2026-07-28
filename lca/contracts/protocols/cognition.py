"""L1 认知 / Brain 协议 —— Reasoner / Critic / BrainStrategy 等。"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from lca.contracts.decision import Observation, Reflection, StructuredDecision
from lca.contracts.state import TypedState


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
class CompletionPolicy(Protocol):
    """确定性收尾策略：校验候选决策是否可被采纳。"""

    async def enforce(
        self,
        state: TypedState,
        decision: StructuredDecision,
    ) -> StructuredDecision: ...


@runtime_checkable
class PromptManager(Protocol):
    def render(self, template_name: str, variables: dict[str, Any]) -> str: ...
    def register_template(self, name: str, template: str, version: str = "1.0") -> None: ...


@runtime_checkable
class SkillRouter(Protocol):
    """运行时动态选择 Prompt 模板 / 工具子集。"""

    async def route(self, state: TypedState) -> str: ...
