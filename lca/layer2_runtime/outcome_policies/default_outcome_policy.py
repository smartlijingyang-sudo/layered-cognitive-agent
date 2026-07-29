"""DefaultStepOutcomePolicy —— 默认单步结果判定策略。"""

from __future__ import annotations

from lca.contracts.decision import Observation, Reflection, StructuredDecision
from lca.contracts.enums import ActionType, ReflectionVerdict
from lca.contracts.lifecycle import TaskStatus
from lca.contracts.protocols import StepOutcome, StepOutcomePolicy
from lca.contracts.state import TypedState


class DefaultStepOutcomePolicy(StepOutcomePolicy):
    def resolve(
        self,
        state: TypedState,
        decision: StructuredDecision | None,
        observation: Observation | None,
        reflection: Reflection | None,
    ) -> StepOutcome:
        if decision is None or reflection is None:
            return StepOutcome()
        degraded_ok = bool(
            observation is not None and observation.success and observation.degraded_from
        )
        if decision.action_type == ActionType.HANDOFF:
            return StepOutcome(should_stop=True, status=TaskStatus.COMPLETED)
        if decision.action_type == ActionType.RESPOND or degraded_ok:
            final_output = decision.response_text if decision.response_text else None
            if (
                final_output is None
                and degraded_ok
                and observation is not None
                and isinstance(observation.payload, str)
            ):
                final_output = observation.payload
            should_stop = reflection.verdict != ReflectionVerdict.NEEDS_CORRECTION
            return StepOutcome(
                should_stop=should_stop,
                final_output=final_output,
                status=TaskStatus.COMPLETED if should_stop else None,
            )
        return StepOutcome()

    def resolve_budget_exceeded(
        self, observation: Observation | None, state: TypedState
    ) -> StepOutcome:
        last_ok = observation is not None and observation.success
        final_output = None
        if (
            last_ok
            and state.final_output is None
            and observation is not None
            and isinstance(observation.payload, str)
        ):
            final_output = observation.payload
        return StepOutcome(
            should_stop=True,
            final_output=final_output,
            status=TaskStatus.COMPLETED if last_ok else TaskStatus.FAILED,
        )
