"""The ADR-0047 wire verdict must survive every LLMResponse → Decision projection.

Regression: ``think.decision.parse`` (the node the live graph schedules) and the
gate's ``DefaultDecisionClassifier`` each carried their own copy of the
native-call mapping and built ``ToolCall`` without ``wire_status`` /
``wire_reason`` / ``wire_raw_preview``. The truncation verdict therefore died
before ``tool_wire_gate`` and ``think.decision.repair`` could read it, and the
model only ever saw a generic ``missing_required_arguments``.
"""

from __future__ import annotations

from lca.cognition.brain.llm_turn.response_projection import project_llm_response
from lca.contracts.atoms.semantic.keys import (
    TOOL_WIRE_RAW_PREVIEW,
    TOOL_WIRE_REASON,
    TOOL_WIRE_STATUS,
)
from lca.contracts.models.core.conversation.llm import LLMResponse, NativeToolCall
from lca.nodes.concept.decision_classify.parse_tool_calls import _parse_response
from lca.nodes.think.decision.parse import _project_response
from lca.plugins.gate.decision_classifier_provider import DefaultDecisionClassifier

_WIRE_REASON = "unterminated_or_truncated_json"
_WIRE_PREVIEW = '{"path": "/mnt/data/report.pdf", "content": "第一行'


def _truncated_call(name: str = "writeFile") -> NativeToolCall:
    return NativeToolCall(
        call_id="call_1",
        name=name,
        arguments={},
        wire_status="incomplete",
        wire_reason=_WIRE_REASON,
        wire_raw_preview=_WIRE_PREVIEW,
    )


def _response(*calls: NativeToolCall, text: str = "") -> LLMResponse:
    return LLMResponse(
        text=text,
        tool_calls=tuple(calls),
        model="test-model",
        finish_reason="tool_calls",
    )


def test_shared_projection_copies_the_wire_verdict() -> None:
    projected = project_llm_response(_response(_truncated_call()))
    call = projected.tool_calls[0]
    assert call.wire_status == "incomplete"
    assert call.wire_reason == _WIRE_REASON
    assert call.wire_raw_preview == _WIRE_PREVIEW


def test_live_think_node_keeps_the_wire_verdict() -> None:
    tool_calls, _, _ = _project_response(_response(_truncated_call()))
    assert tool_calls[0].wire_status == "incomplete"
    assert tool_calls[0].wire_reason == _WIRE_REASON
    assert tool_calls[0].wire_raw_preview == _WIRE_PREVIEW


def test_concept_classify_node_keeps_the_wire_verdict() -> None:
    tool_calls, _, _ = _parse_response(_response(_truncated_call()))
    assert tool_calls[0].wire_status == "incomplete"
    assert tool_calls[0].wire_reason == _WIRE_REASON


def test_gate_classifier_keeps_the_wire_verdict_on_the_decision() -> None:
    decision = DefaultDecisionClassifier().classify(_response(_truncated_call()))
    assert decision.tool_calls[0].wire_status == "incomplete"
    assert decision.tool_calls[0].wire_raw_preview == _WIRE_PREVIEW


def test_well_formed_call_projects_as_ok() -> None:
    call = NativeToolCall(call_id="c", name="listFiles", arguments={"directoryPath": "."})
    projected = project_llm_response(_response(call))
    assert projected.tool_calls[0].wire_status == "ok"
    assert projected.tool_calls[0].arguments == {"directoryPath": "."}


def test_delegate_calls_split_away_from_tool_calls() -> None:
    delegate = NativeToolCall(
        call_id="d",
        name="delegate",
        arguments={"subtask": "总结", "target_role": "writer"},
    )
    projected = project_llm_response(_response(delegate, _truncated_call("readFile")))
    assert [d.subtask for d in projected.delegations] == ["总结"]
    assert [c.tool_name for c in projected.tool_calls] == ["readFile"]


def test_leaked_tool_call_markup_is_recovered_and_stripped_from_intent() -> None:
    projected = project_llm_response(
        _response(text='先看文件\n[Tool call: listFiles]\n{"directoryPath": "."}')
    )
    assert [c.tool_name for c in projected.tool_calls] == ["listFiles"]
    assert projected.tool_calls[0].arguments == {"directoryPath": "."}
    assert projected.intent == "先看文件"


def test_wire_status_reaches_the_decision_extra_used_by_the_body_gate() -> None:
    """``compose_action`` reads the projected fields into ``Decision.extra``."""
    from lca.nodes.concept.decision_classify.compose_action import _wire_extra

    extra = _wire_extra(tuple(_project_response(_response(_truncated_call()))[0]))
    assert extra[TOOL_WIRE_STATUS] == "incomplete"
    assert extra[TOOL_WIRE_REASON] == _WIRE_REASON
    assert extra[TOOL_WIRE_RAW_PREVIEW] == _WIRE_PREVIEW
