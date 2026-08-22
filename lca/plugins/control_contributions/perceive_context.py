"""Perceive-context control executor."""

from __future__ import annotations

from lca.contracts.protocols.declarative_phase_graph import PhaseInput, PhaseResult
from lca.layer2_runtime.control_runtime import ControlVerdict, ControlVerdictKind


class PerceiveContextExecutor:
    """Execute perceive-context control policy."""

    async def execute(self, context: any, input: PhaseInput) -> PhaseResult:
        """Evaluate perceive-context control."""
        state = context.state
        if state.status.value != "working":
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.STOP,
                    detail="run state is not working",
                    plugin_id="control.executor.perceive-context",
                ),
            )
        return PhaseResult(
            result_kind="control",
            payload=ControlVerdict(
                kind=ControlVerdictKind.ALLOW,
                detail="context assembly is permitted",
                plugin_id="control.executor.perceive-context",
            ),
        )
