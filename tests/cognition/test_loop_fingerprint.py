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


def test_listfiles_directory_path_aliases_share_fingerprint() -> None:
    dot = ToolCall(call_id="c1", tool_name="listFiles", arguments={"directoryPath": "."})
    mnt = ToolCall(call_id="c2", tool_name="listFiles", arguments={"directoryPath": "/mnt/data"})
    assert tool_call_fingerprint(dot) == tool_call_fingerprint(mnt)
