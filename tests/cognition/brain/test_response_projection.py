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


# ── Regression: undecodable markup is a wire failure, not an answer ───────
#
# run_c6df7c01ccae returned 15 completion tokens whose whole text was the
# trailing close of an invoke/parameter block. The projection put it in
# ``intent``, ``decision.parse`` classified it ``respond``, and the loop
# committed the fragment as a successful final answer.

_CLOSE_PARAM = "</" + "parameter>"
_CLOSE_FUNC = "</" + "function>"


def test_undecodable_markup_projects_as_an_incomplete_wire_call() -> None:
    projected = project_llm_response(_response(text="`\n\n" + _CLOSE_PARAM + "\n" + _CLOSE_FUNC))
    assert projected.intent == ""
    assert len(projected.tool_calls) == 1
    call = projected.tool_calls[0]
    assert call.tool_name == ""
    assert call.wire_status == "incomplete"
    assert call.wire_reason == _WIRE_REASON
    assert _CLOSE_PARAM in call.wire_raw_preview


def test_decoded_markup_projects_as_a_real_call_not_a_wire_failure() -> None:
    text = (
        'Reading now.\n<tool_calls>\n<invoke name="listFiles">\n'
        '<parameter name="directoryPath">.' + _CLOSE_PARAM + "\n</invoke>\n</tool_calls>"
    )
    projected = project_llm_response(_response(text=text))
    assert projected.intent == "Reading now."
    assert [c.tool_name for c in projected.tool_calls] == ["listFiles"]
    assert projected.tool_calls[0].arguments == {"directoryPath": "."}
    assert projected.tool_calls[0].wire_status == "ok"


def test_native_calls_are_never_reclassified_by_the_text_channel() -> None:
    projected = project_llm_response(
        _response(
            NativeToolCall(call_id="c", name="listFiles", arguments={"directoryPath": "."}),
            text="done " + _CLOSE_FUNC,
        )
    )
    assert [c.tool_name for c in projected.tool_calls] == ["listFiles"]
    assert projected.intent == "done " + _CLOSE_FUNC
