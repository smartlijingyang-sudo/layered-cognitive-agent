"""StopRule — single public concept for “should the cognitive loop stop?”."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from lca.contracts.decision import ActResult, Decision, Reflection
from lca.contracts.lifecycle import TaskStatus
from lca.contracts.state import AgentState


class StopReason(Enum):
    """Why the loop stopped (or continues)."""

    CONTINUE = "continue"
    BUDGET_EXCEEDED = "budget_exceeded"
    TASK_COMPLETED = "task_completed"
    ERROR = "error"


@dataclass(frozen=True)
class StopDecision:
    """Loop's only stop signal — continue or halt with reason/output/status."""

    should_stop: bool = False
    reason: StopReason = StopReason.CONTINUE
    final_output: str | None = None
    status: TaskStatus | None = None

    @property
    def stop(self) -> bool:
        return self.should_stop

    @property
    def output(self) -> str | None:
        return self.final_output


@runtime_checkable
class StopRule(Protocol):
    """Decides after each step whether the cognitive loop continues."""

    def decide(
        self,
        state: AgentState,
        decision: Decision | None,
        act_result: ActResult | None,
        reflection: Reflection | None,
    ) -> StopDecision: ...

    # Transitional name used by CognitiveLoop until fully migrated.
    def judge(
        self,
        state: AgentState,
        decision: Decision | None,
        observation: ActResult | None,
        reflection: Reflection | None,
    ) -> StopDecision: ...
