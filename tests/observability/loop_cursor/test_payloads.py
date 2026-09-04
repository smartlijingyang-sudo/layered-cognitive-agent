"""ADR-0169 PR-1:4 个 payload frozen dataclass 契约测试。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from lca.contracts.observability.loop_cursor_payloads import (
    RequestHeader,
    ThinkingRecord,
    ToolCallRecord,
    ToolResultRecord,
)


def test_thinking_record_frozen() -> None:
    r = ThinkingRecord(
        content_digest="abc",
        content_path=None,
        token_count=100,
        thinking_kind="reasoning",
    )
    with pytest.raises(FrozenInstanceError):
        r.token_count = 200  # type: ignore[misc]


def test_thinking_record_thinking_kind_literal() -> None:
    r = ThinkingRecord(
        content_digest="abc",
        content_path=None,
        token_count=100,
        thinking_kind="compaction",
    )
    assert r.thinking_kind == "compaction"


def test_tool_call_record_call_seq_required() -> None:
    r = ToolCallRecord(
        tool_name="t",
        args_digest="x",
        args_payload_path=None,
        call_seq=1,
    )
    assert r.call_seq == 1


def test_tool_result_record_outcome_literal() -> None:
    r = ToolResultRecord(
        tool_name="t",
        result_digest="x",
        result_path=None,
        outcome="ok",
    )
    assert r.outcome == "ok"


def test_request_header_default_inherited_is_none() -> None:
    h = RequestHeader(
        step_id="step-001",
        incarnation=1,
        reason="initial",
        model="m",
        tools_digest="d2",
        tools_path="p2",
        messages_digest="d3",
        messages_path="p3",
        manifest_digest="d4",
        manifest_path="p4",
    )
    assert h.inherited_from_step is None


def test_request_header_inherited_carries_prev_step() -> None:
    h = RequestHeader(
        step_id="step-002",
        incarnation=1,
        reason="inherited",
        model="m",
        tools_digest="d2",
        tools_path="p2",
        messages_digest="d3",
        messages_path="p3",
        manifest_digest="d4",
        manifest_path="p4",
        inherited_from_step="step-001",
    )
    assert h.inherited_from_step == "step-001"
