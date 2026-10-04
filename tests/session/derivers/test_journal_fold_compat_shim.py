"""INV-08: COMPAT immediate predecessor merge shim invariant tests.

Validates that:
1. Legacy dirty records with empty invocation_id in `target.tool_calls` only merge with the
   immediately preceding unlinked record (window size = 1).
2. If an intermediate call intervened, older empty-id calls are NOT merged across boundaries.
3. Two consecutive real tool calls with identical tool_name and identical arguments are
   NEVER mistakenly merged into a single call. Both calls are preserved as distinct tool calls.
"""

from __future__ import annotations

from typing import Any

from lca.contracts.models.observability.journal.step import ToolCallRecord
from lca.plugins.session.derivers.step_tree.journal_fold import (
    _add_or_update_tool_call,
    _Frame,
    fold_step_tree,
)


def test_compat_shim_merges_only_immediate_predecessor_with_empty_id() -> None:
    """When a legacy dirty tool call with empty invocation_id exists, it merges with immediate predecessor."""
    frame = _Frame(
        step_id="step-001",
        step_index=1,
        phase="think",
        entered_at=1.0,
        tool_calls=[
            ToolCallRecord(invocation_id="", name="bash", arguments={"command": "ls"}),
        ],
    )

    real_record = ToolCallRecord(
        invocation_id="toolu_real_999",
        name="bash",
        arguments={"command": "ls"},
        arguments_summary="",
    )

    _add_or_update_tool_call(frame, real_record)
    assert len(frame.tool_calls) == 1
    assert frame.tool_calls[0].invocation_id == "toolu_real_999"


def test_compat_shim_does_not_merge_across_intermediate_calls() -> None:
    """If an intermediate call already intervened, an older empty-id call is NOT merged (window=1)."""
    frame = _Frame(
        step_id="step-001",
        step_index=1,
        phase="think",
        entered_at=1.0,
        tool_calls=[
            ToolCallRecord(invocation_id="", name="bash", arguments={"command": "pwd"}),
            ToolCallRecord(
                invocation_id="toolu_other_1", name="readFile", arguments={"path": "a.txt"}
            ),
        ],
    )

    real_record = ToolCallRecord(
        invocation_id="toolu_real_bash",
        name="bash",
        arguments={"command": "pwd"},
        arguments_summary="",
    )

    _add_or_update_tool_call(frame, real_record)
    # Because last call is readFile, bash is NOT immediately preceding -> appends, does not merge across!
    assert len(frame.tool_calls) == 3
    assert frame.tool_calls[0].invocation_id == ""
    assert frame.tool_calls[1].invocation_id == "toolu_other_1"
    assert frame.tool_calls[2].invocation_id == "toolu_real_bash"


def test_two_consecutive_identical_tool_calls_are_never_merged() -> None:
    """INV-08: Two consecutive distinct calls with identical args must produce 2 distinct calls."""
    events: list[dict[str, Any]] = [
        {"execution_point": "llm.request.header", "payload": {"step_id": "step-001"}, "when": 1},
        {"execution_point": "phase.think.fold", "payload": {}, "when": 2},
        # First call: ls -la
        {
            "execution_point": "step.tool_call.record",
            "payload": {
                "tool_name": "bash",
                "invocation_id": "toolu_call_alpha",
                "arguments": {"command": "ls -la"},
            },
            "when": 3,
        },
        {
            "execution_point": "step.tool_result.record",
            "payload": {
                "tool_name": "bash",
                "invocation_id": "toolu_call_alpha",
                "ok": True,
                "latency_ms": 12,
                "stdout_head": "file1\nfile2",
            },
            "when": 4,
        },
        # Second call: identical arguments ls -la, but distinct invocation_id!
        {
            "execution_point": "step.tool_call.record",
            "payload": {
                "tool_name": "bash",
                "invocation_id": "toolu_call_beta",
                "arguments": {"command": "ls -la"},
            },
            "when": 5,
        },
        {
            "execution_point": "step.tool_result.record",
            "payload": {
                "tool_name": "bash",
                "invocation_id": "toolu_call_beta",
                "ok": True,
                "latency_ms": 14,
                "stdout_head": "file1\nfile2",
            },
            "when": 6,
        },
    ]

    doc = fold_step_tree(events, run_id="run_two_calls")
    assert len(doc.steps) == 1
    step = doc.steps[0]

    # INV-08: MUST be exactly 2 distinct tool calls and 2 tool results!
    assert len(step.tool_calls) == 2, (
        f"Expected exactly 2 tool calls, got {len(step.tool_calls)}: {step.tool_calls}"
    )
    assert step.tool_calls[0].invocation_id == "toolu_call_alpha"
    assert step.tool_calls[1].invocation_id == "toolu_call_beta"

    assert len(step.tool_results) == 2, (
        f"Expected exactly 2 tool results, got {len(step.tool_results)}: {step.tool_results}"
    )
    assert step.tool_results[0].invocation_id == "toolu_call_alpha"
    assert step.tool_results[1].invocation_id == "toolu_call_beta"
