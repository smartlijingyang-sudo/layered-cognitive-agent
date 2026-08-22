"""Observe-checkpoint control executor."""

from __future__ import annotations

from lca.contracts.protocols.declarative_phase_graph import PhaseInput, PhaseResult
from lca.layer2_runtime.control_runtime import ControlVerdict, ControlVerdictKind


class ObserveCheckpointExecutor:
    """Execute observe-checkpoint control policy."""

    async def execute(self, context: any, input: PhaseInput) -> PhaseResult:
        """Evaluate observe-checkpoint control."""
        if context.state.step < 0:
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.DENY,
                    detail="checkpoint step cannot be negative",
                    plugin_id="control.executor.observe-checkpoint",
                ),
            )
        reason = context.checkpoint_reason.value if context.checkpoint_reason else "periodic"
        return PhaseResult(
            result_kind="control",
            payload=ControlVerdict(
                kind=ControlVerdictKind.ALLOW,
                detail=f"checkpoint is valid: {reason}",
                plugin_id="control.executor.observe-checkpoint",
            ),
        )
