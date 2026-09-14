"""Stop policy delivery-satisfied backup unlocks on live observation success.

Regresses run_2cd22760a828 ls-run loop. The earlier fixture
``test_delivery_satisfied_stops_after_producer_success_without_respond``
relies on ``state.control_turns`` already containing a successful
turn — that fold requires ``commit_turn`` to be called somewhere in
the phase graph (currently zero producers). When the fold is empty
during an in-flight iteration, the policy used to fall through to the
budget guard and burn all 8 max_visits on the same cached tool call.

The backup now also accepts the live ``observation.success`` signal
from the current iteration: if the latest tool call succeeded and
reflection is on-track, ``synthesize_delivery_response`` falls back
to a deterministic placeholder string that is non-empty, so the
policy emits ``StopDecision(should_stop=True)`` instead of
``StopDecision(continue)``.
"""

from __future__ import annotations

from lca.contracts.atoms.enums.enums import ActionType, ReflectionVerdict
from lca.contracts.models.core.execution.decision import (
    Decision,
    Observation,
    Reflection,
    ToolCall,
)
from lca.contracts.models.core.policy.budget import create_budget
from lca.contracts.models.core.state.state import AgentState
from lca.plugins.loop.state.stop_policy.plugin import DefaultStopPolicy


class _StubClosure:
    def synthesize(self) -> str | None:
        return None


def test_delivery_satisfied_stops_via_live_observation_when_fold_empty() -> None:
    state = AgentState(
        trace_id="t",
        task="这个是什么",
        budget=create_budget(max_steps=8),
    )
    # state.control_turns intentionally empty — same as run_2cd22760a828.

    decision = Decision(
        decision_id="d_repeat",
        action_type=ActionType.USE_TOOL,
        rationale="again",
        confidence=0.9,
        tool_calls=[ToolCall(call_id="c1", tool_name="runCommand", arguments={})],
    )
    observation = Observation(
        observation_id="o_repeat",
        success=True,
        payload={"output": "dir listing", "stdout": "dir listing"},
    )
    reflection = Reflection(
        reflection_id="r_repeat",
        verdict=ReflectionVerdict.ON_TRACK,
        lesson=None,
    )

    stop = DefaultStopPolicy(_StubClosure()).decide(state, decision, observation, reflection)
    assert stop.should_stop is True, (
        "Live observation success must unlock the delivery-satisfied backup "
        "even when state.control_turns is empty (fold path has zero producers)."
    )
    assert stop.final_output, "synthesize_delivery_response must return a non-empty string."
    assert stop.reason is not None
    assert stop.status is not None


def test_delivery_satisfied_stops_on_failed_observation_without_tag() -> None:
    """Failed observation with no failure_kind tag still stops the loop.

    Pre-fix (run_0d71855ae274) the deterministic-failure backup only
    fired when ``extra[FAILURE_KIND] == "execution"`` was set, so a
    failed observation that the Body executor never tagged slipped
    through to burn all 8 max_visits. The backup now treats any
    ``success=False`` observation (with a non-empty error) as a
    deterministic failure and stops the loop.
    """
    state = AgentState(
        trace_id="t",
        task="task",
        budget=create_budget(max_steps=8),
    )
    decision = Decision(
        decision_id="d",
        action_type=ActionType.USE_TOOL,
        rationale="x",
        confidence=0.9,
        tool_calls=[ToolCall(call_id="c", tool_name="t", arguments={})],
    )
    observation = Observation(
        observation_id="o",
        success=False,
        payload={},
        error="boom",
    )
    reflection = Reflection(
        reflection_id="r",
        verdict=ReflectionVerdict.ON_TRACK,
        lesson=None,
    )

    stop = DefaultStopPolicy(_StubClosure()).decide(state, decision, observation, reflection)
    assert stop.should_stop is True
    assert stop.reason is not None
    assert stop.status is not None


def test_delivery_satisfied_does_not_stop_on_transient_tag() -> None:
    """Transient failures must remain retriable (model may recover)."""
    from lca.contracts.atoms.semantic.keys import FAILURE_KIND_TRANSIENT

    state = AgentState(
        trace_id="t",
        task="task",
        budget=create_budget(max_steps=8),
    )
    decision = Decision(
        decision_id="d",
        action_type=ActionType.USE_TOOL,
        rationale="x",
        confidence=0.9,
        tool_calls=[ToolCall(call_id="c", tool_name="t", arguments={})],
    )
    observation = Observation(
        observation_id="o",
        success=False,
        payload={},
        error="timeout",
        extra={"failure_kind": FAILURE_KIND_TRANSIENT},
    )
    reflection = Reflection(
        reflection_id="r",
        verdict=ReflectionVerdict.ON_TRACK,
        lesson=None,
    )

    stop = DefaultStopPolicy(_StubClosure()).decide(state, decision, observation, reflection)
    assert stop.should_stop is False


def test_delivery_satisfied_does_not_stop_on_needs_correction() -> None:
    """Negative case: NEEDS_CORRECTION reflection must keep the loop going."""
    state = AgentState(
        trace_id="t",
        task="task",
        budget=create_budget(max_steps=8),
    )
    decision = Decision(
        decision_id="d",
        action_type=ActionType.USE_TOOL,
        rationale="x",
        confidence=0.9,
        tool_calls=[ToolCall(call_id="c", tool_name="t", arguments={})],
    )
    observation = Observation(
        observation_id="o",
        success=True,
        payload={"output": "ok", "stdout": "ok"},
    )
    reflection = Reflection(
        reflection_id="r",
        verdict=ReflectionVerdict.NEEDS_CORRECTION,
        lesson="retry",
    )

    stop = DefaultStopPolicy(_StubClosure()).decide(state, decision, observation, reflection)
    assert stop.should_stop is False
