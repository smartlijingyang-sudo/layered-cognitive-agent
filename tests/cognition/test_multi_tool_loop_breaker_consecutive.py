"""Pin MultiToolLoopBreakerGate against the production repeat distribution.

Origin run: ``run_255698cfe712`` (2026-09-15). Model called ``runCommand echo
TOOL_WORKS && date`` twice with identical args before the phase-graph
``max_visits=2`` budget cut the loop. The gate should have caught the second
call; the production trigger 3 required ``progress_warn=3`` historical turns
and never fired.

These tests pin the new ``LoopPolicyThresholds.consecutive_repeat_max = 2``
default so the regression stays caught.
"""

from __future__ import annotations

import asyncio

from lca.cognition.brain.decision_gates.loop.multi_tool_breaker import (
    MultiToolLoopBreakerGate,
)
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.execution.decision import (
    Decision,
    Observation,
    ToolCall,
    Turn,
)
from lca.contracts.models.core.policy.loop_policy import (
    DEFAULT_LOOP_POLICY,
    LoopPolicyThresholds,
)
from lca.contracts.models.core.state.state import AgentState, Budget
from tests.support.session_gate_helpers import (
    bound_session,
    extend_control_turns,
)


def _run_command_turn(*, arguments: dict[str, object], success: bool = True) -> Turn:
    return Turn(
        decision=Decision(
            decision_id="d-prev",
            action_type=ActionType.USE_TOOL,
            rationale="r",
            confidence=1.0,
            tool_calls=(ToolCall(call_id="c-prev", tool_name="runCommand", arguments=arguments),),
        ),
        observation=Observation(
            observation_id="o-prev", success=success, payload={"stdout": "TOOL_WORKS\n"}
        ),
    )


def test_default_policy_blocks_second_identical_tool_call() -> None:
    """1 prior identical turn + same candidate ⇒ gate must rewrite to RESPOND."""
    args = {"command": "echo TOOL_WORKS && date"}
    with bound_session("consecutive_repeat_2"):
        state = AgentState(trace_id="t", task="demo", budget=Budget())
        extend_control_turns(state, (_run_command_turn(arguments=args),))

        candidate = Decision(
            decision_id="d-cand",
            action_type=ActionType.USE_TOOL,
            rationale="r",
            confidence=1.0,
            tool_calls=(ToolCall(call_id="c-cand", tool_name="runCommand", arguments=args),),
        )

        result = asyncio.run(MultiToolLoopBreakerGate().enforce(state, candidate))

    assert result.action_type == ActionType.RESPOND, (
        f"second identical tool call must be blocked; got {result.action_type}"
    )
    assert result.degraded_from == ActionType.USE_TOOL


def test_default_policy_allows_first_call_when_no_history() -> None:
    """No prior turn + first candidate ⇒ gate passes through unchanged."""
    with bound_session("consecutive_repeat_empty"):
        state = AgentState(trace_id="t", task="demo", budget=Budget())
        candidate = Decision(
            decision_id="d-cand",
            action_type=ActionType.USE_TOOL,
            rationale="r",
            confidence=1.0,
            tool_calls=(
                ToolCall(
                    call_id="c-cand",
                    tool_name="runCommand",
                    arguments={"command": "echo hi"},
                ),
            ),
        )
        result = asyncio.run(MultiToolLoopBreakerGate().enforce(state, candidate))

    assert result.action_type == ActionType.USE_TOOL


def test_default_policy_allows_distinct_arguments() -> None:
    """Same tool, different args ⇒ gate passes through unchanged."""
    with bound_session("consecutive_repeat_diff_args"):
        state = AgentState(trace_id="t", task="demo", budget=Budget())
        extend_control_turns(
            state,
            (_run_command_turn(arguments={"command": "echo a"}),),
        )
        candidate = Decision(
            decision_id="d-cand",
            action_type=ActionType.USE_TOOL,
            rationale="r",
            confidence=1.0,
            tool_calls=(
                ToolCall(
                    call_id="c-cand",
                    tool_name="runCommand",
                    arguments={"command": "echo b"},
                ),
            ),
        )
        result = asyncio.run(MultiToolLoopBreakerGate().enforce(state, candidate))

    assert result.action_type == ActionType.USE_TOOL


def test_profile_can_raise_threshold_to_three() -> None:
    """Profile override: consecutive_repeat_max=3 ⇒ second call still allowed."""
    args = {"command": "echo X"}
    gate = MultiToolLoopBreakerGate(thresholds=LoopPolicyThresholds(consecutive_repeat_max=3))
    with bound_session("consecutive_repeat_3_profile"):
        state = AgentState(trace_id="t", task="demo", budget=Budget())
        extend_control_turns(state, (_run_command_turn(arguments=args),))

        candidate = Decision(
            decision_id="d-cand",
            action_type=ActionType.USE_TOOL,
            rationale="r",
            confidence=1.0,
            tool_calls=(ToolCall(call_id="c-cand", tool_name="runCommand", arguments=args),),
        )
        result = asyncio.run(gate.enforce(state, candidate))

    assert result.action_type == ActionType.USE_TOOL


def test_default_policy_field_value() -> None:
    """Lock the default. If this changes, the regression re-opens silently."""
    assert DEFAULT_LOOP_POLICY.consecutive_repeat_max == 2
