"""Think-guard control executor."""

from __future__ import annotations

from lca.contracts.atoms.enums import ActionType
from lca.contracts.models.core.gate_policy import GateDecided
from lca.contracts.models.core.perceive_state import PerceiveState
from lca.contracts.protocols.declarative_phase_graph import PhaseInput, PhaseResult
from lca.layer2_runtime.control_runtime import ControlVerdict, ControlVerdictKind

_GATE_CONTRIBUTIONS = {
    "gate.repeat-tool-call": "RepeatToolCallGate",
    "gate.tool-loop-breaker": "ToolLoopBreakerGate",
}


def _is_known_action(decision) -> bool:
    """Return whether a decision uses the closed ActionType vocabulary."""
    try:
        ActionType(decision.action_type)
        return True
    except (ValueError, AttributeError):
        return False


def _latest_gate_event(state) -> GateDecided | None:
    """Return the latest typed gate event."""
    # This is a simplified version - in reality we'd need to check plugin_id
    events = PerceiveState.from_agent_state(state).gate_decided
    return events[-1] if events else None


def _gate_verdict_kind(event: GateDecided) -> ControlVerdictKind:
    """Translate the pre-existing GateDecided vocabulary into ControlVerdict."""
    if event.verdict == "rewrite" or event.is_rewritten:
        return ControlVerdictKind.REWRITE
    if event.verdict == "deny":
        return ControlVerdictKind.STOP
    return ControlVerdictKind.ALLOW


class ThinkGuardExecutor:
    """Execute think-guard control policy."""

    async def execute(self, context: any, input: PhaseInput) -> PhaseResult:
        """Evaluate think-guard control."""
        decision = context.decision
        if decision is None:
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.ALLOW,
                    detail="candidate decision not materialized",
                    plugin_id="control.executor.think-guard",
                ),
            )
        if not _is_known_action(decision):
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.STOP,
                    detail="candidate action type is unknown",
                    plugin_id="control.executor.think-guard",
                ),
            )
        event = _latest_gate_event(context.state)
        if event is None:
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.ALLOW,
                    detail="decision gate contribution accepted",
                    plugin_id="control.executor.think-guard",
                ),
            )
        kind = _gate_verdict_kind(event)
        detail = event.rationale or (
            event.policy_fact.message if event.policy_fact is not None else event.verdict
        )
        return PhaseResult(
            result_kind="control",
            payload=ControlVerdict(
                kind=kind,
                detail=detail,
                plugin_id="control.executor.think-guard",
            ),
        )
