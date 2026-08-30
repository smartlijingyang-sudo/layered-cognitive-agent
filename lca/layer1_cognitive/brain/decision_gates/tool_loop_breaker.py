"""Tool loop circuit breaker — stop repeated failing or stalled tool patterns.

The Gate sits in the Think plane and only rewrites a candidate Decision.  It
never executes a tool, mutates an external system, or changes graph topology.
The owning Gate plugin makes this policy profile-selectable.

A failed-call breaker alone is insufficient for an autonomous agent: a model can
consume an entire run by repeatedly issuing an idempotent, successful call that
returns the same observation.  The second branch therefore detects a consecutive
same-tool/same-arguments sequence whose normalized observations are identical.
It deliberately does not block polling-like calls whose observations change.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from hashlib import sha256

from lca.contracts.atoms.enums import ActionType
from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.budget import TOOL_LOOP_BREAK_THRESHOLD
from lca.contracts.models.core.decision import Decision, Observation, ToolCall, Turn
from lca.contracts.models.core.gate_policy import GateDecided, PolicyFact
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import DecisionGate
from lca.layer1_cognitive.brain.decision_gates.chained import record_gate_decided

_BLOCKED_FAILURE_RATIONALE = (
    "同一工具已连续失败多次，禁止再次调用。请换用其他工具、修正代码，或直接 respond 收口。"
)
_BLOCKED_STALLED_RATIONALE = (
    "同一工具以相同参数连续返回相同结果，未观察到新进展，禁止继续重复调用。"
)


class ToolLoopBreakerGate(DecisionGate):
    """Block failed patterns and identical no-progress tool-call loops."""

    async def enforce(self, state: AgentState, decision: Decision) -> Decision:
        if decision.action_type != ActionType.USE_TOOL or not decision.tool_calls:
            return decision

        tool_call = decision.tool_calls[0]
        failure_count = self._consecutive_failures(state, tool_call.tool_name)
        if failure_count >= TOOL_LOOP_BREAK_THRESHOLD:
            return self._block(
                state,
                decision,
                tool_call.tool_name,
                rationale=_BLOCKED_FAILURE_RATIONALE,
                response=self._failure_response(
                    tool_call.tool_name,
                    self._last_tool_error(state, tool_call.tool_name),
                ),
            )

        stalled_count = self._consecutive_identical_observations(state, tool_call)
        if stalled_count >= TOOL_LOOP_BREAK_THRESHOLD:
            return self._block(
                state,
                decision,
                tool_call.tool_name,
                rationale=_BLOCKED_STALLED_RATIONALE,
                response=(
                    f"{tool_call.tool_name} 以相同参数连续返回相同结果 "
                    f"{TOOL_LOOP_BREAK_THRESHOLD} 次，已停止重复调用。"
                ),
            )
        return decision

    def _block(
        self,
        state: AgentState,
        decision: Decision,
        tool_name: str,
        *,
        rationale: str,
        response: str,
    ) -> Decision:
        forced = self._force_respond(decision, rationale=rationale, response=response)
        record_gate_decided(
            state,
            GateDecided(
                event_id=new_id("gate"),
                gate="ToolLoopBreakerGate",
                verdict="rewrite",
                is_rewritten=True,
                tool_name=tool_name,
                rationale=rationale,
                policy_fact=PolicyFact(
                    kind="tool_loop_break",
                    message=forced.response_text or "",
                    source="tool_loop_breaker",
                ),
            ),
        )
        return forced

    @staticmethod
    def _consecutive_failures(state: AgentState, tool_name: str) -> int:
        """Count same-tool failures, preserving the established failure circuit breaker."""

        count = 0
        for turn in reversed(state.history):
            if not isinstance(turn, Turn):
                continue
            tool_call = _first_tool_call(turn)
            if tool_call is None or tool_call.tool_name != tool_name:
                break
            if turn.observation.success:
                break
            count += 1
        return count

    @staticmethod
    def _consecutive_identical_observations(state: AgentState, candidate: ToolCall) -> int:
        """Count equivalent prior calls with an unchanged normalized observation.

        A return value of zero means the sequence contains an unknown/nonportable
        argument or result shape.  Failing open in that situation prevents a
        serialization edge case from turning a valid tool into an unexplainable
        hard stop; the independent failure breaker remains active.
        """

        candidate_fingerprint = _tool_fingerprint(candidate)
        if candidate_fingerprint is None:
            return 0

        count = 0
        expected_observation: str | None = None
        for turn in reversed(state.history):
            if not isinstance(turn, Turn):
                continue
            prior_call = _first_tool_call(turn)
            if prior_call is None or _tool_fingerprint(prior_call) != candidate_fingerprint:
                break
            observation_fingerprint = _observation_fingerprint(turn.observation)
            if observation_fingerprint is None:
                return 0
            if expected_observation is None:
                expected_observation = observation_fingerprint
            elif observation_fingerprint != expected_observation:
                break
            count += 1
        return count

    @staticmethod
    def _last_tool_error(state: AgentState, tool_name: str) -> str:
        """Return the latest same-tool error without leaking unrelated observations."""

        for turn in reversed(state.history):
            if not isinstance(turn, Turn):
                continue
            tool_call = _first_tool_call(turn)
            if tool_call is None or tool_call.tool_name != tool_name:
                continue
            error = (turn.observation.error or "").strip()
            if error:
                return error
        return ""

    @staticmethod
    def _failure_response(tool_name: str, last_error: str) -> str:
        """Create a useful terminal response for the established failure condition."""

        if last_error:
            return (
                f"{tool_name} 连续失败 {TOOL_LOOP_BREAK_THRESHOLD} 次，已停止重试。\n"
                f"最后错误：{last_error}"
            )
        return f"{tool_name} 连续失败 {TOOL_LOOP_BREAK_THRESHOLD} 次，已停止重试。"

    @staticmethod
    def _force_respond(decision: Decision, *, rationale: str, response: str) -> Decision:
        """Preserve Decision identity while converting unsafe continuation into response."""

        return Decision(
            decision_id=decision.decision_id,
            action_type=ActionType.RESPOND,
            rationale=rationale,
            confidence=0.9,
            response_text=response,
        )


def _first_tool_call(turn: Turn) -> ToolCall | None:
    """Return the current single-call decision shape used by the existing gate."""

    decision = turn.decision
    if decision.action_type != ActionType.USE_TOOL or not decision.tool_calls:
        return None
    return decision.tool_calls[0]


def _tool_fingerprint(tool_call: ToolCall) -> str | None:
    """Hash a portable tool identity without treating call ids as semantic progress."""

    payload = _normalize_for_fingerprint(
        {"tool_name": tool_call.tool_name, "arguments": tool_call.arguments}
    )
    if payload is None:
        return None
    return _fingerprint(payload)


def _observation_fingerprint(observation: Observation) -> str | None:
    """Hash success, normalized payload and error to distinguish polling progress."""

    payload = _normalize_for_fingerprint(
        {
            "success": observation.success,
            "payload": observation.payload,
            "error": observation.error,
        }
    )
    if payload is None:
        return None
    return _fingerprint(payload)


def _fingerprint(payload: object) -> str:
    """Return a deterministic SHA-256 digest for one normalized JSON payload."""

    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()


def _normalize_for_fingerprint(value: object) -> object | None:
    """Return a conservative JSON-safe canonical value or ``None`` when unknown.

    Tool arguments and observations may contain arbitrary Python objects in tests
    or third-party adapters.  The policy only compares stable primitives,
    mappings, sequences and sets; it never falls back to ``str(value)`` because
    object representations can embed memory addresses and create false progress.
    """

    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        normalized_mapping: dict[str, object] = {}
        for key in sorted(value, key=lambda item: str(item)):
            if not isinstance(key, str):
                return None
            normalized_value = _normalize_for_fingerprint(value[key])
            if normalized_value is None and value[key] is not None:
                return None
            normalized_mapping[key] = normalized_value
        return normalized_mapping
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        normalized_sequence: list[object] = []
        for item in value:
            normalized_value = _normalize_for_fingerprint(item)
            if normalized_value is None and item is not None:
                return None
            normalized_sequence.append(normalized_value)
        return normalized_sequence
    if isinstance(value, (set, frozenset)):
        normalized_set: list[object] = []
        for item in value:
            normalized_value = _normalize_for_fingerprint(item)
            if normalized_value is None and item is not None:
                return None
            normalized_set.append(normalized_value)
        return sorted(
            normalized_set,
            key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True),
        )
    return None


__all__ = ["ToolLoopBreakerGate"]
