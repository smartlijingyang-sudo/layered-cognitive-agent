"""L2 Runtime 协议 —— 认知循环入口。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.budget import DEFAULT_MAX_STEPS
from lca.contracts.decision import Decision, Observation, Reflection
from lca.contracts.result import Result
from lca.contracts.run_context import RunContext
from lca.contracts.state import AgentState, StateSnapshot
from lca.contracts.types import StopOutcome


@runtime_checkable
class Runtime(Protocol):
    """认知循环入口：驱动 perceive → think → act → reflect 循环。"""

    async def run(
        self,
        task: str,
        ctx: RunContext | None = None,
        *,
        max_steps: int = DEFAULT_MAX_STEPS,
        max_wall_clock_seconds: int | None = None,
        agent_role: str = "",
    ) -> Result: ...
    async def resume(
        self,
        snapshot: StateSnapshot,
        input: object | None = None,
        max_steps: int = DEFAULT_MAX_STEPS,
    ) -> Result: ...


@runtime_checkable
class StopOutcomePolicy(Protocol):
    """单步结果判定策略：决定 Loop 是否继续、最终输出和状态。
    由 StopRule 组合使用，不再直接被 Runtime 持有。
    """

    def resolve(
        self,
        state: AgentState,
        decision: Decision | None,
        observation: Observation | None,
        reflection: Reflection | None,
    ) -> StopOutcome: ...
    def resolve_budget_exceeded(
        self,
        observation: Observation | None,
        state: AgentState,
    ) -> StopOutcome: ...
