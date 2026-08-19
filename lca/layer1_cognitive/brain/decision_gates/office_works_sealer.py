"""Seal Office Works before user-facing respond (LobeHub completion-time scan).

PR4: rewrite verdicts MUST record a GateDecided event.  This gate is a
side-effect gate, not a Decision rewriter; it just records an allow
verdict (which is intentionally NOT recorded per spec §3.5).
"""

from __future__ import annotations

from lca.contracts.atoms.enums import ActionType
from lca.contracts.models.core.budget import TERMINAL_RESERVE_STEPS
from lca.contracts.models.core.decision import Decision
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import DecisionGate
from lca.layer0_infra.workspace.office_works import seal_office_works


class OfficeWorksSealer(DecisionGate):
    """Flush + publish Office outputs when the turn is about to close."""

    async def enforce(self, state: AgentState, decision: Decision) -> Decision:
        if not _should_seal(state, decision):
            return decision
        await seal_office_works()
        return decision


def _should_seal(state: AgentState, decision: Decision) -> bool:
    if decision.action_type in {ActionType.RESPOND, ActionType.STOP, ActionType.ASK_HUMAN}:
        return True
    max_steps = state.budget.max_steps or 0
    return state.step >= max(0, max_steps - TERMINAL_RESERVE_STEPS)
