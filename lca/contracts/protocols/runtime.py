"""L2 Runtime 协议 —— 认知循环入口。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from lca.contracts.decision import Observation, Reflection, StructuredDecision
from lca.contracts.protocols.cognition import CandidateEvaluationPipeline
from lca.contracts.result import Result
from lca.contracts.state import StateSnapshot, TypedState
from lca.contracts.team_progress import DelegationLedgerProtocol
from lca.contracts.types import StepOutcome


@runtime_checkable
class Runtime(Protocol):
    async def run(
        self,
        task: str,
        max_steps: int,
        max_wall_clock_seconds: int | None = None,
        team_progress: DelegationLedgerProtocol | None = None,
        **context: str,
    ) -> Result: ...
    async def resume(
        self, snapshot: StateSnapshot, input: object | None = None, max_steps: int = 10
    ) -> Result: ...
    def wrap_evaluation_pipeline(
        self, wrapper: Callable[[CandidateEvaluationPipeline], CandidateEvaluationPipeline]
    ) -> None: ...


@runtime_checkable
class StepOutcomePolicy(Protocol):
    """单步结果判定策略：决定 Loop 是否继续、最终输出和状态。

    由 LoopJudge 组合使用，不再直接被 Runtime 持有。
    """

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
