"""INV-02: Journal fold zero duplicate tool calls and results invariant tests.

Validates that:
1. `llm.request.header.assistant` never appends or contaminates `target.tool_calls`.
2. `step.tool_call.record` is the single source of truth for tool calls in steps.
3. `body.tool.execute.end` does not duplicate `step.tool_result.record`.
4. Exactly one tool call and one tool result are produced for one actual execution.
"""

from __future__ import annotations

import json
from typing import Any

from lca.plugins.session.derivers.step_tree.journal_fold import fold_step_tree


def test_llm_request_header_assistant_does_not_duplicate_tool_calls() -> None:
    """llm.request.header.assistant with tool_calls must NOT produce duplicate tool_calls in step."""
    events: list[dict[str, Any]] = [
        {
            "execution_point": "llm.request.header",
            "payload": {"step_id": "step-001", "model": "qwen"},
            "when": 1,
        },
        {
            "execution_point": "phase.think.fold",
            "payload": {},
            "when": 2,
        },
        # Model output with predicted tool calls (invocation_id often empty or model-generated)
        {
            "execution_point": "llm.request.header.assistant",
            "payload": {
                "assistant_content": "",
                "tool_calls": [
                    {
                        "id": "",
                        "type": "function",
                        "function": {
                            "name": "tool_search",
                            "arguments": json.dumps({"namespace": "ext"}),
                        },
                    }
                ],
            },
            "when": 3,
        },
        # Real execution event from SafeExecutor with authoritative invocation_id
        {
            "execution_point": "step.tool_call.record",
            "payload": {
                "tool_name": "tool_search",
                "invocation_id": "toolu_real_12345",
                "arguments": {"namespace": "ext"},
                "arguments_summary": "namespace='ext'",
            },
            "when": 4,
        },
        # Real result event
        {
            "execution_point": "step.tool_result.record",
            "payload": {
                "tool_name": "tool_search",
                "invocation_id": "toolu_real_12345",
                "ok": True,
                "latency_ms": 15,
                "stdout_head": "found 3 tools",
            },
            "when": 5,
        },
        # Decision-level outer bracket event with different invocation_id
        {
            "execution_point": "body.tool.execute.end",
            "payload": {
                "tool_name": "tool_search",
                "invocation_id": "decision_4f9e0f4670c7",
                "outcome": "success",
                "ok": True,
                "latency_ms": 16,
            },
            "when": 6,
        },
    ]

    doc = fold_step_tree(events, run_id="run_test_zero_dup")
    assert len(doc.steps) == 1
    step = doc.steps[0]

    # INV-02: Exactly 1 tool_call and 1 tool_result, NO duplicate!
    assert len(step.tool_calls) == 1, (
        f"Expected exactly 1 tool_call, got {len(step.tool_calls)}: {step.tool_calls}"
    )
    assert step.tool_calls[0].name == "tool_search"
    assert step.tool_calls[0].invocation_id == "toolu_real_12345"

    assert len(step.tool_results) == 1, (
        f"Expected exactly 1 tool_result, got {len(step.tool_results)}: {step.tool_results}"
    )
    assert step.tool_results[0].invocation_id == "toolu_real_12345"
    assert step.tool_results[0].stdout_head == "found 3 tools"
