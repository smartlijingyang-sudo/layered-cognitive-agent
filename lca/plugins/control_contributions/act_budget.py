"""Act-budget control executor."""

from __future__ import annotations

from lca.contracts.protocols.declarative_phase_graph import PhaseInput, PhaseResult
from lca.layer2_runtime.control_runtime import ControlVerdict, ControlVerdictKind


class ActBudgetExecutor:
    """Execute act-budget control policy."""

    async def execute(self, context: any, input: PhaseInput) -> PhaseResult:
        """Evaluate act-budget control."""
        if context.state.budget.exceeded():
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.EXHAUSTED,
                    detail="run budget is exhausted",
                    plugin_id="control.executor.act-budget",
                ),
            )
        return PhaseResult(
            result_kind="control",
            payload=ControlVerdict(
                kind=ControlVerdictKind.ALLOW,
                detail="run budget remains available",
                plugin_id="control.executor.act-budget",
            ),
        )
