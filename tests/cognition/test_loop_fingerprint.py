"""Tests for shared loop fingerprint helpers."""

from __future__ import annotations

from lca.cognition.brain.decision_gates.loop.fingerprint import (
    normalize_for_fingerprint,
    tool_call_fingerprint,
)
from lca.contracts.models.core.execution.decision import ToolCall


def test_tool_call_fingerprint_stable_for_same_args() -> None:
    call = ToolCall(call_id="c1", tool_name="runCommand", arguments={"cmd": "ls"})
    assert tool_call_fingerprint(call) == tool_call_fingerprint(call)


def test_normalize_rejects_non_json_safe_objects() -> None:
    assert normalize_for_fingerprint(object()) is None
