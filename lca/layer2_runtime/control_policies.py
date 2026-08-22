"""Concrete policy evaluation for the ADR-0074 ControlPlan.

The control plan owns *which* contributions are active.  This module owns the
pure, deterministic decision made by each active contribution from the current
run facts.  It has no side effects and never mutates ``AgentState``; the
runtime maps the aggregated outcome to phase behavior.
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.enums import ActionType, SnapshotReason
from lca.contracts.models.core.decision import Decision, Observation, Reflection
from lca.contracts.models.core.gate_policy import GateDecided
from lca.contracts.models.core.perceive_state import PerceiveState
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols.control_plan import ControlEntry
from lca.layer2_runtime.control_runtime import (
    ControlSelection,
    ControlVerdict,
    ControlVerdictKind,
)


@dataclass(frozen=True, slots=True)
class ControlPolicyContext:
    """Facts available to a control contribution at its owning loop boundary."""

    state: AgentState
    decision: Decision | None = None
    observation: Observation | None = None
    reflection: Reflection | None = None
    checkpoint_reason: SnapshotReason | None = None


class DefaultControlPolicyEngine:
    """Evaluate the standard profile's concrete control contributions.

    The engine deliberately uses only phase-local, already materialized facts:
    it neither reads live workspaces nor invokes tools.  A profile can still
    retain the constitutional ``control.default.*`` no-op entry; that entry is
    explicitly evaluated as allow and is never mistaken for a real policy.
    """

    def evaluate(
        self,
        selection: ControlSelection,
        context: ControlPolicyContext,
    ) -> tuple[ControlVerdict, ...]:
        """Return exactly one verdict per active plan contribution in plan order."""
        return tuple(
            self._evaluate_entry(entry, selection.slot, context) for entry in selection.entries
        )

    def _evaluate_entry(
        self,
        entry: ControlEntry,
        slot: ControlSlot,
        context: ControlPolicyContext,
    ) -> ControlVerdict:
        if entry.plugin_id.startswith("control.default."):
            return self._verdict(entry, ControlVerdictKind.ALLOW, "constitutional no-op fallback")
        if slot is ControlSlot.PERCEIVE_CONTEXT:
            return self._perceive_context(entry, context)
        if slot is ControlSlot.THINK_GUARD:
            return self._think_guard(entry, context)
        if slot is ControlSlot.ACT_AUTHORIZE:
            return self._act_authorize(entry, context)
        if slot is ControlSlot.ACT_BUDGET:
            return self._act_budget(entry, context)
        if slot is ControlSlot.ACT_CONSTRAIN:
            return self._act_constrain(entry, context)
        if slot is ControlSlot.ACT_EXECUTE:
            return self._act_execute(entry, context)
        if slot is ControlSlot.ACT_SAFE_BOUNDARY:
            return self._act_safe_boundary(entry, context)
        if slot is ControlSlot.REMEMBER_ADMIT:
            return self._remember_admit(entry, context)
        if slot is ControlSlot.STOP_DECIDE:
            return self._stop_decide(entry, context)
        if slot is ControlSlot.OBSERVE_CHECKPOINT:
            return self._observe_checkpoint(entry, context)
        if slot is ControlSlot.OBSERVE_WILDCARD:
            return self._verdict(entry, ControlVerdictKind.ALLOW, "observe contribution recorded")
        raise ValueError(f"unsupported control slot: {slot.value}")

    @staticmethod
    def _verdict(
        entry: ControlEntry,
        kind: ControlVerdictKind,
        detail: str,
    ) -> ControlVerdict:
        return ControlVerdict(plugin_id=entry.plugin_id, kind=kind, detail=detail)

    def _perceive_context(
        self,
        entry: ControlEntry,
        context: ControlPolicyContext,
    ) -> ControlVerdict:
        if context.state.status.value != "working":
            return self._verdict(entry, ControlVerdictKind.STOP, "run state is not working")
        return self._verdict(entry, ControlVerdictKind.ALLOW, "context assembly is permitted")

    def _think_guard(
        self,
        entry: ControlEntry,
        context: ControlPolicyContext,
    ) -> ControlVerdict:
        if context.decision is None:
            return self._verdict(
                entry, ControlVerdictKind.ALLOW, "candidate decision not materialized"
            )
        if not _is_known_action(context.decision):
            return self._verdict(entry, ControlVerdictKind.STOP, "candidate action type is unknown")
        event = _latest_gate_event(entry.plugin_id, context.state)
        if event is None:
            return self._verdict(
                entry, ControlVerdictKind.ALLOW, "decision gate contribution accepted"
            )
        kind = _gate_verdict_kind(event)
        detail = event.rationale or (
            event.policy_fact.message if event.policy_fact is not None else event.verdict
        )
        return self._verdict(entry, kind, detail)

    def _act_authorize(
        self,
        entry: ControlEntry,
        context: ControlPolicyContext,
    ) -> ControlVerdict:
        decision = context.decision
        if decision is None or not _is_known_action(decision):
            return self._verdict(entry, ControlVerdictKind.DENY, "action type is not authorized")
        if decision.action_type == ActionType.USE_TOOL:
            if not decision.tool_calls:
                return self._verdict(entry, ControlVerdictKind.DENY, "tool action has no tool call")
            if any(not call.tool_name.strip() for call in decision.tool_calls):
                return self._verdict(
                    entry, ControlVerdictKind.DENY, "tool action has an unnamed tool"
                )
        return self._verdict(entry, ControlVerdictKind.ALLOW, "action shape is authorized")

    def _act_budget(
        self,
        entry: ControlEntry,
        context: ControlPolicyContext,
    ) -> ControlVerdict:
        if context.state.budget.exceeded():
            return self._verdict(entry, ControlVerdictKind.EXHAUSTED, "run budget is exhausted")
        return self._verdict(entry, ControlVerdictKind.ALLOW, "run budget remains available")

    def _act_constrain(
        self,
        entry: ControlEntry,
        context: ControlPolicyContext,
    ) -> ControlVerdict:
        decision = context.decision
        if decision is None:
            return self._verdict(
                entry, ControlVerdictKind.DENY, "action constraint needs a decision"
            )
        call_ids = [call.call_id for call in decision.tool_calls]
        if any(not call_id.strip() for call_id in call_ids):
            return self._verdict(entry, ControlVerdictKind.DENY, "tool call id is required")
        if len(set(call_ids)) != len(call_ids):
            return self._verdict(entry, ControlVerdictKind.DENY, "tool call ids must be unique")
        if any(call.timeout_s is not None and call.timeout_s <= 0 for call in decision.tool_calls):
            return self._verdict(entry, ControlVerdictKind.DENY, "tool timeout must be positive")
        return self._verdict(entry, ControlVerdictKind.ALLOW, "action constraints are satisfied")

    def _act_execute(
        self,
        entry: ControlEntry,
        context: ControlPolicyContext,
    ) -> ControlVerdict:
        decision = context.decision
        if decision is None:
            return self._verdict(entry, ControlVerdictKind.DENY, "execution requires a decision")
        if decision.action_type == ActionType.USE_TOOL and not decision.tool_calls:
            return self._verdict(entry, ControlVerdictKind.DENY, "tool execution has no calls")
        if (
            decision.action_type in {ActionType.DELEGATE, ActionType.HANDOFF}
            and not decision.delegations
        ):
            return self._verdict(
                entry, ControlVerdictKind.DENY, "delegation execution has no target"
            )
        return self._verdict(entry, ControlVerdictKind.ALLOW, "execution payload is complete")

    def _act_safe_boundary(
        self,
        entry: ControlEntry,
        context: ControlPolicyContext,
    ) -> ControlVerdict:
        if context.state.status.value != "working":
            return self._verdict(
                entry, ControlVerdictKind.DENY, "non-working run cannot cross body boundary"
            )
        decision = context.decision
        if decision is not None and decision.action_type == ActionType.STOP:
            return self._verdict(entry, ControlVerdictKind.STOP, "decision requested terminal stop")
        return self._verdict(entry, ControlVerdictKind.ALLOW, "body boundary is safe")

    def _remember_admit(
        self,
        entry: ControlEntry,
        context: ControlPolicyContext,
    ) -> ControlVerdict:
        if context.observation is None or context.reflection is None:
            return self._verdict(
                entry, ControlVerdictKind.DENY, "memory admission requires outcome and reflection"
            )
        if context.state.status.value != "working":
            return self._verdict(
                entry, ControlVerdictKind.DENY, "terminal run does not admit new memory"
            )
        return self._verdict(entry, ControlVerdictKind.ALLOW, "turn is admissible to memory")

    def _stop_decide(
        self,
        entry: ControlEntry,
        context: ControlPolicyContext,
    ) -> ControlVerdict:
        if context.state.budget.exceeded():
            return self._verdict(entry, ControlVerdictKind.STOP, "run budget is exhausted")
        if context.decision is not None and context.decision.action_type == ActionType.STOP:
            return self._verdict(entry, ControlVerdictKind.STOP, "decision requested terminal stop")
        return self._verdict(entry, ControlVerdictKind.ALLOW, "stop rule may continue")

    def _observe_checkpoint(
        self,
        entry: ControlEntry,
        context: ControlPolicyContext,
    ) -> ControlVerdict:
        if context.state.step < 0:
            return self._verdict(
                entry, ControlVerdictKind.DENY, "checkpoint step cannot be negative"
            )
        reason = context.checkpoint_reason.value if context.checkpoint_reason else "periodic"
        return self._verdict(entry, ControlVerdictKind.ALLOW, f"checkpoint is valid: {reason}")


_GATE_CONTRIBUTIONS: dict[str, str] = {
    "gate.repeat-tool-call": "RepeatToolCallGate",
    "gate.tool-loop-breaker": "ToolLoopBreakerGate",
}


def _latest_gate_event(plugin_id: str, state: AgentState) -> GateDecided | None:
    """Return the latest typed gate event owned by one concrete contribution."""
    expected_gate = _GATE_CONTRIBUTIONS.get(plugin_id)
    if expected_gate is None:
        return None
    events = PerceiveState.from_agent_state(state).gate_decided
    return next((event for event in reversed(events) if event.gate == expected_gate), None)


def _gate_verdict_kind(event: GateDecided) -> ControlVerdictKind:
    """Translate the pre-existing GateDecided vocabulary into ControlVerdict."""
    if event.verdict == "rewrite" or event.is_rewritten:
        return ControlVerdictKind.REWRITE
    if event.verdict == "deny":
        return ControlVerdictKind.REWRITE
    return ControlVerdictKind.ALLOW


def _is_known_action(decision: Decision) -> bool:
    """Return whether a decision uses the closed ActionType vocabulary."""
    try:
        ActionType(decision.action_type)
    except ValueError:
        return False
    return True


__all__ = ["ControlPolicyContext", "DefaultControlPolicyEngine"]
