"""Act-safe-boundary control executor."""

from __future__ import annotations

from lca.contracts.atoms.enums import ActionType
from lca.contracts.protocols.declarative_phase_graph import PhaseInput, PhaseResult
from lca.layer2_runtime.control_runtime import ControlVerdict, ControlVerdictKind


class ActSafeBoundaryExecutor:
    """Execute act-safe-boundary control policy."""

    async def execute(self, context: any, input: PhaseInput) -> PhaseResult:
        """Evaluate act-safe-boundary control."""
        if context.state.status.value != "working":
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.DENY,
                    detail="non-working run cannot cross body boundary",
                    plugin_id="control.executor.act-safe-boundary",
                ),
            )
        decision = context.decision
        if decision is not None and decision.action_type == ActionType.STOP:
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.STOP,
                    detail="decision requested terminal stop",
                    plugin_id="control.executor.act-safe-boundary",
                ),
            )
        return PhaseResult(
            result_kind="control",
            payload=ControlVerdict(
                kind=ControlVerdictKind.ALLOW,
                detail="body boundary is safe",
                plugin_id="control.executor.act-safe-boundary",
            ),
        )
