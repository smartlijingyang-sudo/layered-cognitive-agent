"""Stop policy delivery-satisfied backup (ADR-0196 CV4)."""

from __future__ import annotations

from lca.contracts.atoms.enums.enums import ActionType, ReflectionVerdict
from lca.contracts.models.core.execution.decision import (
    Decision,
    Observation,
    Reflection,
    ToolCall,
    Turn,
)
from lca.contracts.models.core.policy.budget import create_budget
from lca.contracts.models.core.state.state import AgentState
from lca.plugins.loop.state.stop_policy.plugin import DefaultStopPolicy


class _StubClosure:
    def synthesize(self) -> str | None:
        return None


def test_delivery_satisfied_stops_after_producer_success_without_respond() -> None:
    state = AgentState(
        trace_id="t",
        task="这个是什么",
        budget=create_budget(max_steps=8),
    )
    state.control_turns.append(
        Turn(
            decision=Decision(
                decision_id="d0",
                action_type=ActionType.USE_TOOL,
                rationale="read",
                confidence=0.9,
                tool_calls=[ToolCall(call_id="c0", tool_name="executeCode", arguments={})],
            ),
            observation=Observation(
                observation_id="o0",
                success=True,
                payload={"stdout": "算力资源使用报告模板\n" + ("章节\n" * 20)},
            ),
        )
    )
    decision = Decision(
        decision_id="d1",
        action_type=ActionType.USE_TOOL,
        rationale="again",
        confidence=0.9,
        tool_calls=[ToolCall(call_id="c1", tool_name="activate_skill", arguments={})],
    )
    reflection = Reflection(
        reflection_id="r1",
        verdict=ReflectionVerdict.ON_TRACK,
        lesson="ok",
    )
    stop = DefaultStopPolicy(_StubClosure()).decide(state, decision, None, reflection)
    assert stop.should_stop is True
    assert stop.final_output
    assert "算力" in stop.final_output or "交付" in stop.final_output or "工作区" in stop.final_output


# ---------------------------------------------------------------------------
# Deterministic-failure stop: tool returned a non-recoverable error
# (PermissionError, TypeError, etc., tagged FAILURE_KIND_EXECUTION in
# ``observation.extra``).  Retrying the same call is futile, so the loop
# should halt on the first deterministic failure instead of cycling the
# model through 8 identical tool calls.
# ---------------------------------------------------------------------------


def test_deterministic_tool_failure_stops_loop() -> None:
    from lca.contracts.atoms.enums.enums import ReflectionVerdict as _RV
    from lca.contracts.atoms.semantic.keys import FAILURE_KIND, FAILURE_KIND_EXECUTION
    from lca.contracts.models.core.execution.decision import (
        Decision as _D,
        Observation as _O,
        Reflection as _R,
        ToolCall as _T,
    )
    from lca.contracts.models.core.policy.budget import create_budget as _cb
    from lca.contracts.models.core.state.lifecycle import TaskStatus
    from lca.contracts.models.core.state.state import AgentState as _S
    from lca.contracts.models.core.policy.stop import StopReason
    from lca.plugins.loop.state.stop_policy.plugin import DefaultStopPolicy as _DSP

    state = _S(trace_id="t", task="读 /etc/hostname", budget=_cb(max_steps=8))
    obs = _O(
        observation_id="o0",
        success=False,
        payload=None,
        error="PermissionError: [Errno 13] Permission denied: '/etc/grub2.cfg'",
        extra={FAILURE_KIND: FAILURE_KIND_EXECUTION},
    )
    state.control_turns.append(
        Turn(
            decision=_D(
                decision_id="d0",
                action_type=ActionType.USE_TOOL,
                rationale="read",
                confidence=0.9,
                tool_calls=[_T(call_id="c0", tool_name="listFiles", arguments={})],
            ),
            observation=obs,
        )
    )
    decision = _D(
        decision_id="d1",
        action_type=ActionType.USE_TOOL,
        rationale="retry",
        confidence=0.9,
        tool_calls=[_T(call_id="c1", tool_name="listFiles", arguments={})],
    )
    reflection = _R(reflection_id="r1", verdict=_RV.ON_TRACK, lesson="ok")
    stop = _DSP(_StubClosure()).decide(state, decision, obs, reflection)
    assert stop.should_stop is True
    assert stop.reason == StopReason.ERROR
    assert stop.status == TaskStatus.FAILED
