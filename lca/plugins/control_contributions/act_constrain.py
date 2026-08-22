"""Act-constrain control executor."""

from __future__ import annotations

from lca.contracts.protocols.declarative_phase_graph import PhaseInput, PhaseResult
from lca.layer2_runtime.control_runtime import ControlVerdict, ControlVerdictKind


class ActConstrainExecutor:
    """Execute act-constrain control policy."""

    async def execute(self, context: any, input: PhaseInput) -> PhaseResult:
        """Evaluate act-constrain control."""
        decision = context.decision
        if decision is None:
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.DENY,
                    detail="action constraint needs a decision",
                    plugin_id="control.executor.act-constrain",
                ),
            )
        call_ids = [call.call_id for call in decision.tool_calls]
        if any(not call_id.strip() for call_id in call_ids):
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.DENY,
                    detail="tool call id is required",
                    plugin_id="control.executor.act-constrain",
                ),
            )
        if len(set(call_ids)) != len(call_ids):
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.DENY,
                    detail="tool call ids must be unique",
                    plugin_id="control.executor.act-constrain",
                ),
            )
        if any(call.timeout_s is not None and call.timeout_s <= 0 for call in decision.tool_calls):
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.DENY,
                    detail="tool timeout must be positive",
                    plugin_id="control.executor.act-constrain",
                ),
            )
        return PhaseResult(
            result_kind="control",
            payload=ControlVerdict(
                kind=ControlVerdictKind.ALLOW,
                detail="action constraints are satisfied",
                plugin_id="control.executor.act-constrain",
            ),
        )
