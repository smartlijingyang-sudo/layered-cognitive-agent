"""L2 Runtime 协议 —— 认知循环入口与单步结果判定。"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from lca.contracts.decision import Observation, Reflection, StructuredDecision
from lca.contracts.result import Result
from lca.contracts.state import TypedState
from lca.contracts.types import StepOutcome


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
class StepOutcomePolicy(Protocol):
    """单步结果判定策略：决定 Loop 是否继续、最终输出和状态。"""

    def resolve(
        self,
        state: TypedState,
        decision: StructuredDecision | None,
        observation: Observation | None,
        reflection: Reflection | None,
    ) -> StepOutcome: ...

    def resolve_budget_exceeded(
        self,
        observation: Observation | None,
        state: TypedState,
    ) -> StepOutcome: ...
