"""Terminal respond gate — reserve last step for user-facing closure (ADR-0051 + PR6).

PR4: rewrite verdicts MUST record a GateDecided event.  When the gate
forces a respond, a GateDecided event with verdict=rewrite is recorded.

PR6: the gate reads workspace artifacts **exclusively** from the typed
``PerceiveState.current_manifest`` artifact items.  Live
``get_run_workspace()`` reads from the Reasoner / Gates are forbidden
(v3 §5.1) — the workspace is a Sensor-owned surface.
"""

from __future__ import annotations

from lca.contracts.atoms.enums import ActionType
from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.budget import TERMINAL_RESERVE_STEPS
from lca.contracts.models.core.decision import Decision
from lca.contracts.models.core.gate_policy import GateDecided, PolicyFact
from lca.contracts.models.core.perceive_state import PerceiveState
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import DecisionGate
from lca.cognition.brain.decision_gates.chained import record_gate_decided

_TERMINAL_RATIONALE = "终态步：必须向用户收口；产物已从工作区账本合成摘要。"

# Last-step writes still run. Forcing respond here would ship a stale ledger
# and discard the tool that was about to produce the deliverable.
_PRODUCER_TOOLS = frozenset(
    {
        "editFile",
        "executeCode",
        "exportFile",
        "runCommand",
        "sandbox_execute",
        "writeFile",
        "write_file_local",
        "local_runCommand",
        "local_writeFile",
        "local_editFile",
        "local_executeCode",
        "local_readFile",
    }
)


def _closure_from_manifest(state: AgentState) -> str:
    """Read the workspace-artifacts manifest item as the closure source (PR6).

    Pre-PR6 this called ``get_run_workspace().artifacts.closure_text()``
    directly.  v3 §5.1 forbids live workspace reads in Gates — the
    Hub's ``WorkspaceArtifactsSensor`` is the only legitimate source.
    """
    manifest = PerceiveState.from_agent_state(state).current_manifest
    if manifest is None:
        return ""
    for item in manifest.items:
        if item.kind != "workspace_artifacts":
            continue
        if not isinstance(item.payload, list) or not item.payload:
            continue
        lines: list[str] = []
        for art in item.payload:
            if isinstance(art, dict):
                path = art.get("path", "")
                url = art.get("url", "")
                lines.append(f"- {path} {url}")
        return "\n".join(lines)
    return ""


class TerminalRespondGate(DecisionGate):
    """Force respond on last step for non-producing tool actions."""

    async def enforce(self, state: AgentState, decision: Decision) -> Decision:
        max_steps = state.budget.max_steps or 0
        reserve = TERMINAL_RESERVE_STEPS
        if state.step < max(0, max_steps - reserve):
            return decision
        if decision.action_type in {ActionType.RESPOND, ActionType.STOP, ActionType.ASK_HUMAN}:
            return decision
        if _is_producer(decision):
            return decision

        closure = _closure_from_manifest(state)
        response = closure or decision.response_text or "任务已完成。"
        forced = Decision(
            decision_id=decision.decision_id,
            action_type=ActionType.RESPOND,
            rationale=_TERMINAL_RATIONALE,
            confidence=decision.confidence,
            response_text=response,
        )
        record_gate_decided(
            state,
            GateDecided(
                event_id=new_id("gate"),
                gate="TerminalRespondGate",
                verdict="rewrite",
                is_rewritten=True,
                policy_fact=PolicyFact(
                    kind="terminal_respond",
                    message=_TERMINAL_RATIONALE,
                    source="terminal_respond",
                ),
            ),
        )
        return forced


def _is_producer(decision: Decision) -> bool:
    if decision.action_type != ActionType.USE_TOOL or not decision.tool_calls:
        return False
    return decision.tool_calls[0].tool_name in _PRODUCER_TOOLS
