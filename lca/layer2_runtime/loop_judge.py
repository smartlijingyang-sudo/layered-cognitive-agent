"""DefaultLoopJudge —— 组合 StepOutcomePolicy + Budget 的默认终止裁判。

将原先散落在 CognitiveRuntime._loop 中的三种终止判定
（budget 超限 / outcome 策略 / 异常状态）收敛为单一内聚类。
"""

from __future__ import annotations

from lca.contracts.decision import Observation, Reflection, StructuredDecision
from lca.contracts.lifecycle import TaskStatus
from lca.contracts.loop_judge import LoopJudge, TerminationReason, TerminationSignal
from lca.contracts.protocols import StepOutcomePolicy
from lca.contracts.state import TypedState


class DefaultLoopJudge(LoopJudge):
    """默认循环终止裁判。

    组合 StepOutcomePolicy（业务判定）与 Budget 检查（资源约束），
    输出统一的 TerminationSignal。
    """

    def __init__(self, outcome_policy: StepOutcomePolicy) -> None:
        self._outcome_policy = outcome_policy

    def judge(
        self,
        state: TypedState,
        decision: StructuredDecision | None,
        observation: Observation | None,
        reflection: Reflection | None,
    ) -> TerminationSignal:
        outcome = self._outcome_policy.resolve(state, decision, observation, reflection)
        if outcome.final_output is not None:
            state.final_output = outcome.final_output

        if state.budget.exceeded():
            return self._on_budget_exceeded(observation, state)

        if outcome.should_stop:
            return TerminationSignal(
                should_stop=True,
                reason=TerminationReason.TASK_COMPLETED,
                final_output=state.final_output if isinstance(state.final_output, str) else None,
                status=_coerce_status(outcome.status) or TaskStatus.COMPLETED,
            )

        return TerminationSignal()

    def _on_budget_exceeded(
        self,
        observation: Observation | None,
        state: TypedState,
    ) -> TerminationSignal:
        budget_outcome = self._outcome_policy.resolve_budget_exceeded(observation, state)
        if budget_outcome.final_output is not None:
            state.final_output = budget_outcome.final_output
        return TerminationSignal(
            should_stop=True,
            reason=TerminationReason.BUDGET_EXCEEDED,
            final_output=state.final_output if isinstance(state.final_output, str) else None,
            status=_coerce_status(budget_outcome.status) or TaskStatus.FAILED,
        )


_STATUS_MAP: dict[str, TaskStatus] = {
    "completed": TaskStatus.COMPLETED,
    "failed": TaskStatus.FAILED,
    "working": TaskStatus.WORKING,
    "running": TaskStatus.WORKING,
    "waiting_human": TaskStatus.INPUT_REQUIRED,
    "input_required": TaskStatus.INPUT_REQUIRED,
    "input-required": TaskStatus.INPUT_REQUIRED,
    "canceled": TaskStatus.CANCELED,
    "cancelled": TaskStatus.CANCELED,
}


def _coerce_status(value: str | TaskStatus | None) -> TaskStatus | None:
    if value is None:
        return None
    if isinstance(value, TaskStatus):
        return value
    return _STATUS_MAP.get(str(value), TaskStatus.COMPLETED)


__all__ = ["DefaultLoopJudge"]
