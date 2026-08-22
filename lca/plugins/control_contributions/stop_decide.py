"""Stop-decide control executor."""

from __future__ import annotations

from lca.contracts.atoms.enums import ActionType
from lca.contracts.protocols.declarative_phase_graph import PhaseInput, PhaseResult
from lca.layer2_runtime.control_runtime import ControlVerdict, ControlVerdictKind


class StopDecideExecutor:
    """Execute stop-decide control policy."""

    async def execute(self, context: any, input: PhaseInput) -> PhaseResult:
        """Evaluate stop-decide control."""
        if context.state.budget.exceeded():
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.STOP,
                    detail="run budget is exhausted",
                    plugin_id="control.executor.stop-decide",
                ),
            )
        if context.decision is not None and context.decision.action_type == ActionType.STOP:
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.STOP,
                    detail="decision requested terminal stop",
                    plugin_id="control.executor.stop-decide",
                ),
            )
        return PhaseResult(
            result_kind="control",
            payload=ControlVerdict(
                kind=ControlVerdictKind.ALLOW,
                detail="stop rule may continue",
                plugin_id="control.executor.stop-decide",
            ),
        )
