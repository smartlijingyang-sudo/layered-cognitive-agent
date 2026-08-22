"""Act-execute control executor."""

from __future__ import annotations

from lca.contracts.atoms.enums import ActionType
from lca.contracts.protocols.declarative_phase_graph import PhaseInput, PhaseResult
from lca.layer2_runtime.control_runtime import ControlVerdict, ControlVerdictKind


class ActExecuteExecutor:
    """Execute act-execute control policy."""

    async def execute(self, context: any, input: PhaseInput) -> PhaseResult:
        """Evaluate act-execute control."""
        decision = context.decision
        if decision is None:
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.DENY,
                    detail="execution requires a decision",
                    plugin_id="control.executor.act-execute",
                ),
            )
        if decision.action_type == ActionType.USE_TOOL and not decision.tool_calls:
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.DENY,
                    detail="tool execution has no calls",
                    plugin_id="control.executor.act-execute",
                ),
            )
        if (
            decision.action_type in {ActionType.DELEGATE, ActionType.HANDOFF}
            and not decision.delegations
        ):
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.DENY,
                    detail="delegation execution has no target",
                    plugin_id="control.executor.act-execute",
                ),
            )
        return PhaseResult(
            result_kind="control",
            payload=ControlVerdict(
                kind=ControlVerdictKind.ALLOW,
                detail="execution payload is complete",
                plugin_id="control.executor.act-execute",
            ),
        )
