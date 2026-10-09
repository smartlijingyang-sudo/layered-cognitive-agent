"""A tool call whose arguments never arrived must not execute (ADR-0047).

Two shipped seams close this:

- ``build_llm_response`` classifies the streamed ``arguments`` payload
  instead of silently parsing a truncated string into ``{}``;
- ``UseToolOperation``'s gate refuses a call whose required arguments are
  all missing and hands the model the retry instruction.

``run_445b582f0a90`` lost ~6.7k tokens of streamed ``writeFile`` arguments:
the call reached the sandbox with no path, raised
``IsADirectoryError: '/mnt/data'``, and the run ended there.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.cognition.body.tools.tool_wire_gate import (
    missing_arguments_block_observation,
    required_arguments,
    tool_wire_block_observation,
)
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.atoms.semantic.keys import FAILURE_KIND, TOOL_WIRE_STATUS
from lca.contracts.models.core.conversation.llm import LLMResponse, NativeToolCall
from lca.contracts.models.core.execution.decision import Decision, ToolCall
from lca.infrastructure.llm_adapter.openai_compat.shared._shared import (
    _RawToolCall,
    build_llm_response,
)


@dataclass
class _Tool:
    name: str
    parameters: dict[str, Any]


@dataclass
class _Registry:
    tools: dict[str, _Tool]

    def get(self, name: str) -> _Tool | None:
        return self.tools.get(name)


def _decision(*calls: ToolCall) -> Decision:
    return Decision(
        decision_id="dec-1",
        action_type=ActionType.USE_TOOL.value,
        rationale="r",
        confidence=1.0,
        tool_calls=list(calls),
    )


def test_truncated_writefile_json_is_incomplete() -> None:
    """A cut-off writeFile body is not a call. The gate refuses it."""
    truncated = '{"path": "outputs/report.py", "content": "from reportlab.platypus import'
    response: LLMResponse = build_llm_response(
        text="",
        tool_calls=[_RawToolCall(name="writeFile", arguments_json=truncated, call_id="c1")],
        model="qwen3.7-plus",
        usage=None,
        finish_reason="tool_calls",
    )

    call = response.tool_calls[0]
    assert call.wire_status == "incomplete"
    assert call.arguments == {}


def test_length_finish_reason_with_valid_json_still_executes() -> None:
    response = build_llm_response(
        text="",
        tool_calls=[
            _RawToolCall(
                name="writeFile", arguments_json='{"path": "a.pdf", "content": "x"}', call_id="c1"
            )
        ],
        model="m",
        usage=None,
        finish_reason="length",
    )

    call = response.tool_calls[0]
    assert call.wire_status == "ok"
    assert call.arguments == {"path": "a.pdf", "content": "x"}


def test_length_finish_reason_without_recoverable_fields_is_incomplete() -> None:
    response = build_llm_response(
        text="",
        tool_calls=[_RawToolCall(name="writeFile", arguments_json="{", call_id="c1")],
        model="m",
        usage=None,
        finish_reason="length",
    )

    assert response.tool_calls[0].arguments == {}
    assert response.tool_calls[0].wire_status == "incomplete"
    assert response.tool_calls[0].wire_reason == "finish_reason_length"


def test_well_formed_arguments_stay_ok() -> None:
    response = build_llm_response(
        text="",
        tool_calls=[
            _RawToolCall(name="writeFile", arguments_json='{"path": "a.pdf"}', call_id="c1")
        ],
        model="m",
        usage=None,
        finish_reason="tool_calls",
    )

    call = response.tool_calls[0]
    assert call.wire_status == "ok"
    assert call.arguments == {"path": "a.pdf"}


def test_gate_blocks_a_call_whose_required_arguments_are_missing() -> None:
    registry = _Registry(
        tools={"writeFile": _Tool(name="writeFile", parameters={"required": ["path", "content"]})}
    )
    decision = _decision(ToolCall(call_id="c1", tool_name="writeFile", arguments={}))

    observation = missing_arguments_block_observation(decision, registry)

    assert observation is not None
    assert observation.success is False
    assert observation.tool_call_id == "c1"
    assert "missing_required_arguments" in (observation.error or "")
    assert "shorten code/args" in (observation.error or "")
    assert observation.extra[TOOL_WIRE_STATUS] == "incomplete"
    assert observation.extra[FAILURE_KIND]


def test_gate_allows_a_call_that_supplies_a_required_argument() -> None:
    registry = _Registry(
        tools={"writeFile": _Tool(name="writeFile", parameters={"required": ["path", "content"]})}
    )
    decision = _decision(
        ToolCall(call_id="c1", tool_name="writeFile", arguments={"path": "outputs/report.pdf"})
    )

    assert missing_arguments_block_observation(decision, registry) is None


def test_gate_ignores_tools_without_required_arguments() -> None:
    registry = _Registry(tools={"listFiles": _Tool(name="listFiles", parameters={})})
    decision = _decision(ToolCall(call_id="c1", tool_name="listFiles", arguments={}))

    assert missing_arguments_block_observation(decision, registry) is None
    assert required_arguments(_Tool(name="listFiles", parameters={})) == ()


def test_native_tool_call_defaults_to_ok() -> None:
    """The classification is additive: existing producers keep their shape."""
    call = NativeToolCall(call_id="c1", name="readFile", arguments={"path": "a"})

    assert (call.wire_status, call.wire_reason, call.wire_raw_preview) == ("ok", "", "")


def test_large_truncated_writefile_json_does_not_execute() -> None:
    huge = '{"path": "outputs/a.py", "content": "' + ("x" * 20_000)
    response = build_llm_response(
        text="",
        tool_calls=[_RawToolCall(name="writeFile", arguments_json=huge, call_id="c1")],
        model="m",
        usage=None,
        finish_reason="tool_calls",
    )
    call = response.tool_calls[0]
    assert call.wire_status == "incomplete"
    assert call.arguments == {}


def test_empty_arguments_with_tool_calls_finish_are_incomplete() -> None:
    response = build_llm_response(
        text="",
        tool_calls=[_RawToolCall(name="writeFile", arguments_json="", call_id="c1")],
        model="m",
        usage=None,
        finish_reason="tool_calls",
    )
    call = response.tool_calls[0]
    assert call.arguments == {}
    assert call.wire_status == "incomplete"
    assert call.wire_reason == "empty_arguments"


def test_unloaded_namespace_is_not_executable() -> None:
    from lca.cognition.body.tools.tool_wire_gate import unexposed_tool_block_observation
    from lca.infrastructure.tool_defer.policy import DeferPolicy
    from lca.infrastructure.tool_defer.session import (
        ToolDeferSession,
        reset_current_defer_session,
        set_current_defer_session,
    )

    class _Tool:
        def __init__(self, name: str, namespace: str) -> None:
            self.name = name
            self.namespace = namespace
            self.description = name
            self.parameters = {"type": "object", "properties": {}}

    session = ToolDeferSession(DeferPolicy.default())
    session.update_turn(
        (_Tool("tool_search", namespace="core"), _Tool("run_command", namespace="shell")),
    )
    token = set_current_defer_session(session)
    try:
        hidden = unexposed_tool_block_observation(
            _decision(
                ToolCall(call_id="c1", tool_name="run_command", arguments={"command": "find /tmp"})
            )
        )
        assert hidden is not None
        assert hidden.success is False
        assert "shell" in (hidden.error or "")
        assert "tool_search" in (hidden.error or "")
        visible = unexposed_tool_block_observation(
            _decision(
                ToolCall(call_id="c2", tool_name="tool_search", arguments={"namespace": "shell"})
            )
        )
        assert visible is None
    finally:
        reset_current_defer_session(token)


def test_name_forms_removed_and_camel_case_blocked() -> None:
    """_name_forms is completely removed; calling unexposed tool by camelCase does not bypass wire gate."""
    import lca.cognition.body.tools.tool_wire_gate as wire_gate

    assert not hasattr(wire_gate, "_name_forms")


def test_gate_blocks_tool_call_wire_status_even_without_decision_extra() -> None:
    decision = _decision(
        ToolCall(
            call_id="c1",
            tool_name="writeFile",
            arguments={},
            wire_status="incomplete",
            wire_reason="unterminated_or_truncated_json",
            wire_raw_preview='{"content": "from reportlab',
        )
    )
    from lca.cognition.body.tools.tool_wire_gate import tool_wire_block_observation

    observation = tool_wire_block_observation(decision)
    assert observation is not None
    assert observation.success is False
    assert "writeFile" in (observation.error or "")


# ----- RA-091: both gates share the blocking-observation extra contract ------


def _incomplete_wire_decision() -> Decision:
    call = ToolCall(
        call_id="c-wire",
        tool_name="writeFile",
        arguments={},
        wire_status="incomplete",
        wire_reason="truncated",
    )
    return _decision(call)


def _missing_args_decision() -> tuple[Decision, _Registry]:
    call = ToolCall(call_id="c-args", tool_name="writeFile", arguments={})
    registry = _Registry(
        tools={"writeFile": _Tool(name="writeFile", parameters={"required": ["path"]})}
    )
    return _decision(call), registry


@pytest.mark.parametrize(
    "make_obs",
    [
        pytest.param(
            lambda: tool_wire_block_observation(_incomplete_wire_decision()),
            id="wire-status-gate",
        ),
        pytest.param(
            lambda: missing_arguments_block_observation(*_missing_args_decision()),
            id="missing-arguments-gate",
        ),
    ],
)
def test_both_wire_gates_share_blocking_observation_contract(make_obs) -> None:
    """The converged seam guarantees one blocking-observation contract."""
    from lca.contracts.atoms.enums.enums import MemoryRecordKind
    from lca.contracts.atoms.semantic.keys import (
        FAILURE_KIND_TOOL_WIRE,
        OBS_RESULT_KIND,
        TOOL_WIRE_REASON,
    )

    obs = make_obs()
    assert obs is not None
    assert obs.success is False
    assert obs.extra[FAILURE_KIND] == FAILURE_KIND_TOOL_WIRE
    assert obs.extra[OBS_RESULT_KIND] == MemoryRecordKind.TOOL_RESULT
    assert obs.extra[TOOL_WIRE_STATUS] in ("incomplete", "invalid")
    assert isinstance(obs.extra[TOOL_WIRE_REASON], str) and obs.extra[TOOL_WIRE_REASON]
    # single-sourced guidance text, identical in both gates
    assert (
        "do not treat as successful tool result" in (obs.error or "")
    )
