"""Act-authorize control executor."""

from __future__ import annotations

from lca.contracts.atoms.enums import ActionType
from lca.contracts.protocols.declarative_phase_graph import PhaseInput, PhaseResult
from lca.layer2_runtime.control_runtime import ControlVerdict, ControlVerdictKind


def _is_known_action(decision) -> bool:
    """Return whether a decision uses the closed ActionType vocabulary."""
    try:
        ActionType(decision.action_type)
        return True
    except (ValueError, AttributeError):
        return False


class ActAuthorizeExecutor:
    """Execute act-authorize control policy."""

    async def execute(self, context: any, input: PhaseInput) -> PhaseResult:
        """Evaluate act-authorize control."""
        decision = context.decision
        if decision is None or not _is_known_action(decision):
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.DENY,
                    detail="action type is not authorized",
                    plugin_id="control.executor.act-authorize",
                ),
            )
        if decision.action_type == ActionType.USE_TOOL:
            if not decision.tool_calls:
                return PhaseResult(
                    result_kind="control",
                    payload=ControlVerdict(
                        kind=ControlVerdictKind.DENY,
                        detail="tool action has no tool call",
                        plugin_id="control.executor.act-authorize",
                    ),
                )
            if any(not call.tool_name.strip() for call in decision.tool_calls):
                return PhaseResult(
                    result_kind="control",
                    payload=ControlVerdict(
                        kind=ControlVerdictKind.DENY,
                        detail="tool action has an unnamed tool",
                        plugin_id="control.executor.act-authorize",
                    ),
                )
        return PhaseResult(
            result_kind="control",
            payload=ControlVerdict(
                kind=ControlVerdictKind.ALLOW,
                detail="action shape is authorized",
                plugin_id="control.executor.act-authorize",
            ),
        )
