"""ADR-0047 tool-arguments classification — regression coverage.

Every case here is an argument shape observed on the wire in
``traces/runs/run_3b656790bb67`` / ``run_d2a1c51bf821`` / ``run_96c98cf7249f``:
complete JSON that the classifier reported as ``unterminated_or_truncated_json``,
which made the Body refuse the call and the loop re-ask the model forever.
"""

from __future__ import annotations

import pytest

from lca.infrastructure.llm_adapter.tool.arguments import (
    ToolArgumentsIncomplete,
    ToolArgumentsOk,
    resolve_tool_arguments,
)


@pytest.mark.parametrize(
    "raw",
    [
        '{"directoryPath": "."}',
        '{"directoryPath": "/files"}',
        '{"directory": "/files", "keyword": "3月"}',
        '{"questions": [{"header": "名称", "options": [{"label": "小助手"}]}]}',
        '{"count": 3}',
        '{"recursive": true}',
        '{"nested": {"a": {"b": [1, 2]}}}',
        '{"path": ""}',
    ],
)
def test_complete_json_object_is_ok_regardless_of_key_names(raw: str) -> None:
    """A payload that parses is executable; the recovery key list is not an allowlist."""
    outcome = resolve_tool_arguments(raw, finish_reason="tool_calls")
    assert isinstance(outcome, ToolArgumentsOk)


def test_complete_json_object_is_ok_even_when_finish_reason_is_length() -> None:
    outcome = resolve_tool_arguments('{"directoryPath": "."}', finish_reason="length")
    assert isinstance(outcome, ToolArgumentsOk)
    assert outcome.arguments == {"directoryPath": "."}


def test_empty_object_stays_ok_so_body_names_the_missing_argument() -> None:
    """``{}`` is a complete payload; the required-argument gate owns that error."""
    outcome = resolve_tool_arguments("{}", finish_reason="tool_calls")
    assert isinstance(outcome, ToolArgumentsOk)
    assert outcome.arguments == {}


def test_non_dict_json_is_wrapped() -> None:
    outcome = resolve_tool_arguments("[1, 2]", finish_reason="tool_calls")
    assert isinstance(outcome, ToolArgumentsOk)
    assert outcome.arguments == {"_value": [1, 2]}


def test_truncated_payload_with_recoverable_text_body_is_ok() -> None:
    raw = '{"path": "/mnt/data/report.pdf", "content": "第一行\n第二行'
    outcome = resolve_tool_arguments(raw, finish_reason="tool_calls")
    assert isinstance(outcome, ToolArgumentsOk)
    assert outcome.arguments["path"] == "/mnt/data/report.pdf"
    assert outcome.arguments["content"].startswith("第一行")


def test_truncated_payload_without_recoverable_field_is_incomplete() -> None:
    outcome = resolve_tool_arguments('{"directoryPath":', finish_reason="tool_calls")
    assert isinstance(outcome, ToolArgumentsIncomplete)
    assert outcome.reason == "unterminated_or_truncated_json"


def test_blank_arguments_on_a_tool_call_are_incomplete() -> None:
    outcome = resolve_tool_arguments("", finish_reason="tool_calls")
    assert isinstance(outcome, ToolArgumentsIncomplete)
    assert outcome.reason == "empty_arguments"


def test_blank_arguments_without_a_tool_call_finish_are_ok() -> None:
    outcome = resolve_tool_arguments(None, finish_reason="stop")
    assert isinstance(outcome, ToolArgumentsOk)
    assert outcome.arguments == {}


def test_length_finish_without_recoverable_field_reports_length() -> None:
    outcome = resolve_tool_arguments('{"queries": [1, 2', finish_reason="length")
    assert isinstance(outcome, ToolArgumentsIncomplete)
    assert outcome.reason == "finish_reason_length"
