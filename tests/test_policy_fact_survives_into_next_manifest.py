"""PR4: PolicyFact emitted by RepeatToolCallGate reaches the next ContextManifest.

Mechanical test for the v3 contract:

> step 0 emits a GateDecided → step 1's Manifest contains a PolicyFact
> derived from it (per spec §5.5).

The test deliberately drives the real shipped code: ``RepeatToolCallGate``
+ ``record_gate_decided`` + the typed ``PerceiveState`` view.  No
mocking of the gate internals.
"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.decision import Decision, ToolCall, Turn
from lca.contracts.models.core.perceive_state import PerceiveState
from lca.contracts.models.core.state import AgentState, Budget
from lca.layer1_cognitive.brain.decision_gates import RepeatToolCallGate


def _state() -> AgentState:
    budget = Budget(max_steps=10)
    return AgentState(trace_id=new_id("trace"), task="t", budget=budget)


def _tool_decision(tool: str) -> Decision:
    return Decision(
        decision_id=new_id("dec"),
        action_type="use_tool",
        rationale="x",
        confidence=0.5,
        tool_calls=[ToolCall(call_id=new_id("tc"), tool_name=tool, arguments={})],
    )


def _bucket(state: AgentState) -> list:
    return PerceiveState.from_agent_state(state).gate_decided


@pytest.mark.asyncio
async def test_repeat_tool_call_emits_policy_fact() -> None:
    state = _state()
    tool = "executeCode"
    # Three consecutive failures of the same tool.
    for _ in range(3):
        state.history.append(
            Turn(
                decision=_tool_decision(tool),
                observation=_failed_obs(tool),
            )
        )
    gate = RepeatToolCallGate()
    decision = _tool_decision(tool)
    out = await gate.enforce(state, decision)
    # The decision is NOT rewritten (warning only).
    assert out is decision
    # The bucket holds one GateDecided with a PolicyFact.
    bucket = _bucket(state)
    assert len(bucket) == 1
    event = bucket[0]
    assert event.gate == "RepeatToolCallGate"
    assert event.verdict == "warn"
    assert event.is_rewritten is False
    assert event.policy_fact is not None
    assert event.policy_fact.kind == "repeat_tool_call"
    assert tool in event.policy_fact.message


@pytest.mark.asyncio
async def test_warnings_accumulate_so_next_manifest_can_fold() -> None:
    """The bucket is the input edge for the next ContextManifest's fold.

    The actual fold lives in ``PerceiveHub`` (PR3a).  This test asserts the
    invariant the fold relies on: the typed ``gate_decided`` view is a
    list of frozen ``GateDecided`` events, in order, ready to be folded.
    """
    state = _state()
    gate = RepeatToolCallGate()
    # Trigger one warning.
    state.history.extend(
        Turn(
            decision=_tool_decision("executeCode"),
            observation=_failed_obs("executeCode"),
        )
        for _ in range(3)
    )
    await gate.enforce(state, _tool_decision("executeCode"))
    bucket = _bucket(state)
    assert len(bucket) == 1
    pf = bucket[0].policy_fact
    # The fold pass picks these up and surfaces them in the next
    # ContextManifest.  The fold itself is exercised in
    # tests/test_journal_reducer_apply_delta_equivalent_to_fold_events.py.
    assert pf is not None
    assert pf.source == "repeat_tool_call"


def _failed_obs(tool: str):
    from lca.contracts.models.core.decision import Observation

    return Observation(
        observation_id=new_id("obs"),
        success=False,
        payload="",
        error="boom",
        tool_call_id="x",
    )
