"""Remember-admit control executor."""

from __future__ import annotations

from lca.contracts.protocols.declarative_phase_graph import PhaseInput, PhaseResult
from lca.layer2_runtime.control_runtime import ControlVerdict, ControlVerdictKind


class RememberAdmitExecutor:
    """Execute remember-admit control policy."""

    async def execute(self, context: any, input: PhaseInput) -> PhaseResult:
        """Evaluate remember-admit control."""
        if context.observation is None or context.reflection is None:
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.DENY,
                    detail="memory admission requires outcome and reflection",
                    plugin_id="control.executor.remember-admit",
                ),
            )
        if context.state.status.value != "working":
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.DENY,
                    detail="terminal run does not admit new memory",
                    plugin_id="control.executor.remember-admit",
                ),
            )
        return PhaseResult(
            result_kind="control",
            payload=ControlVerdict(
                kind=ControlVerdictKind.ALLOW,
                detail="turn is admissible to memory",
                plugin_id="control.executor.remember-admit",
            ),
        )
