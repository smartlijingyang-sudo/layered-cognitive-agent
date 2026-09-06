"""Replay API tests (ADR-0198)."""

from __future__ import annotations

from lca.plugins.session.derivers.step_tree.journal_fold import fold_step_tree
from lca_kernel.events.compile.replay import replay_projection


def test_replay_journal_step_tree() -> None:
    events = [
        {
            "execution_point": "writable.step.start",
            "payload": {"step_id": "step_001", "phase": "think"},
            "when": 1.0,
        },
        {
            "execution_point": "writable.step.end",
            "payload": {"outcome": "success"},
            "when": 2.0,
        },
    ]
    doc = replay_projection(events, "journal.step_tree", run_id="r_replay", outcome="completed")
    assert doc.totals.steps == 1


def test_replay_matches_live_fold_for_tool_evidence() -> None:
    events = [
        {"execution_point": "brain.think.start", "payload": {}, "when": 1.0},
        {
            "execution_point": "step.tool_call.record",
            "payload": {
                "invocation_id": "inv-1",
                "tool_name": "grep",
                "arguments": {"pattern": "x"},
                "arguments_summary": '{"pattern":"x"}',
            },
            "when": 1.1,
        },
        {
            "execution_point": "body.tool.execute.start",
            "payload": {"tool_name": "grep", "invocation_id": "inv-1", "arguments": {}},
            "when": 1.2,
        },
        {
            "execution_point": "step.tool_result.record",
            "payload": {
                "ok": True,
                "stdout_head": "match",
                "latency_ms": 3,
                "delta_summary": "found",
            },
            "when": 1.3,
        },
        {"execution_point": "brain.think.end", "payload": {}, "when": 2.0},
    ]
    kwargs = {"run_id": "r_parity", "outcome": "completed"}
    live = fold_step_tree(events, **kwargs)
    replayed = replay_projection(events, "journal.step_tree", **kwargs)
    assert live.steps[0].tool_call == replayed.steps[0].tool_call
    assert live.steps[0].tool_result == replayed.steps[0].tool_result

