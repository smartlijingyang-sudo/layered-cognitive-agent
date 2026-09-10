"""M5 — DecisionTrace / ControlTrace / ToolCallTrace / LLMCallTrace / ReducerApply."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lca.contracts.observability.observation import (
    ControlTrace,
    DecisionTrace,
    LLMCallTrace,
    ReducerApply,
    ToolCallTrace,
)


def test_decision_trace_accepted_and_rejected_paths() -> None:
    d_acc = DecisionTrace(
        run_id="r",
        decision_id="d1",
        source_node_id="think.main",
        accepted=True,
        action_type="use_TOOL",
        occurred_at="t",
    )
    d_rej = DecisionTrace(
        run_id="r",
        decision_id="d2",
        source_node_id="think.main",
        accepted=False,
        action_type=None,
        occurred_at="t",
    )
    assert d_acc.accepted is True
    assert d_rej.accepted is False


def test_control_trace_deny_with_clause() -> None:
    c = ControlTrace(
        run_id="r",
        source_node_id="act.main",
        control_slot="act.authorize",
        verdict="deny",
        reason="action type is not authorized",
        contract_clause="art.action.action_type",
        occurred_at="t",
    )
    assert c.contract_clause == "art.action.action_type"


def test_tool_call_trace_with_retry() -> None:
    t = ToolCallTrace(
        run_id="r",
        source_node_id="x",
        tool_name="search",
        args={"q": "x"},
        result={"hits": 1},
        success=True,
        elapsed_ms=200,
        retry_count=2,
        occurred_at="t",
    )
    assert t.retry_count == 2


def test_llm_call_trace_token_usage_dict() -> None:
    ll = LLMCallTrace(
        run_id="r",
        source_node_id="x",
        model="gpt-5",
        prompt_digest="p",
        response_digest="r",
        token_usage={"prompt": 100, "completion": 50},
        occurred_at="t",
    )
    assert ll.token_usage["prompt"] == 100


def test_reducer_apply_phase_boundary_flag() -> None:
    r = ReducerApply(
        run_id="r",
        method="apply_step_advanced",
        outcome="success",
        phase_boundary=True,
        occurred_at="t",
    )
    assert r.phase_boundary is True


def test_event_traces_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        DecisionTrace(
            run_id="r",
            decision_id="d",
            source_node_id="x",
            accepted=True,
            occurred_at="t",
            unknown="x",  # type: ignore[call-arg]
        )
