"""RepeatToolCallGate — emits PolicyFact warnings via GateDecided (PR4 / v3 §3.5).

Detects the simplest \"loop\" pattern: the same tool called repeatedly with
no semantic variation.  Unlike ``ToolLoopBreakerGate`` (which *blocks* after
a threshold of consecutive failures), this gate is a warning emitter:

- Threshold 3 (same tool_name, consecutive)
- Compares tool_name only (no payload diffing)
- Never fills ``degraded_from`` — it is a warning, not a degradation
- Emits a PolicyFact via the journal's GateDecided chain so the next
  ``ContextManifest`` carries the warning into the prompt without the
  Reasoner ever reading ``state.working_memory[\"loop_warning\"]``.
"""

from __future__ import annotations

from lca.cognition.brain.decision_gates.chained import record_gate_decided
from lca.contracts.atoms.enums import ActionType
from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.decision import Decision, Turn
from lca.contracts.models.core.gate_policy import GateDecided, PolicyFact
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import DecisionGate

_THRESHOLD = 3
_FACT_KIND = "repeat_tool_call"
_WARNING_TEMPLATE = (
    "⚠️ 你已连续 {count} 次调用工具 {tool}{failed}。请换一种方法或工具，不要继续重复相同的调用。"
)


class RepeatToolCallGate(DecisionGate):
    """Warn (not block) on consecutive identical tool calls.

    The PolicyFact is recorded via the ``record_gate_decided`` helper.  When
    the Journal emits a ``GateDecided`` event, the next ``ContextManifest``
    automatically picks it up (perceive-side fold).  The Reasoner never
    reads ``state.working_memory\"loop_warning\"`` — that path is gone.
    """

    async def enforce(self, state: AgentState, decision: Decision) -> Decision:
        if decision.action_type != ActionType.USE_TOOL or not decision.tool_calls:
            return decision

        tool_name = decision.tool_calls[0].tool_name
        consecutive = self._consecutive_same_tool(state, tool_name)
        if consecutive < _THRESHOLD:
            return decision

        # Build the warning payload.  is_rewritten=False: this is a warning,
        # not a structural rewrite of the decision.
        last_obs = state.history[-1].observation if state.history else None
        failed = bool(last_obs is not None and not last_obs.success)
        message = _WARNING_TEMPLATE.format(
            count=consecutive,
            tool=tool_name,
            failed="，且最近调用失败" if failed else "",
        )

        record_gate_decided(
            state,
            GateDecided(
                event_id=new_id("gate"),
                gate="RepeatToolCallGate",
                verdict="warn",
                is_rewritten=False,
                tool_name=tool_name,
                policy_fact=PolicyFact(
                    kind=_FACT_KIND,
                    message=message,
                    source="repeat_tool_call",
                ),
            ),
        )
        return decision

    @staticmethod
    def _consecutive_same_tool(state: AgentState, tool_name: str) -> int:
        count = 0
        for turn in reversed(state.history):
            if not isinstance(turn, Turn):
                break
            dec = turn.decision
            if dec.action_type != ActionType.USE_TOOL or not dec.tool_calls:
                break
            if dec.tool_calls[0].tool_name != tool_name:
                break
            count += 1
        return count
