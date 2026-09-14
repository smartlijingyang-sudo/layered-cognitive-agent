"""Tests for ``lca-ops debug-graph`` (one-shot run debugger).

Pins the contract: read spine SSOT → emit graph skeleton + per-node
input/output payload + reducer sequence + llm calls + auto root-cause
markers. Works even when ``journal.json`` has not materialized (which
breaks ``debug-run`` / ``explain``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from lca.infrastructure.cli.cli.cli import app
from lca.infrastructure.cli.commands.observation.debug_graph import (
    build_debug_graph,
)


@pytest.fixture
def fake_run_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a minimal trace dir with a spine.jsonl mimicking the real shape."""
    monkeypatch.chdir(tmp_path)
    run_id = "run_test_debug_graph"
    run_dir = tmp_path / "traces" / "runs" / run_id
    run_dir.mkdir(parents=True)
    spine = run_dir / f"{run_id}.spine.jsonl"
    events = [
        {"event_id": "x:1", "execution_point": "kernel.run.start", "payload": {"run_id": run_id}},
        {
            "event_id": "x:2", "execution_point": "phase_graph.node.start",
            "payload": {"node_id": "phase.perceive.observe", "visit_index": 1, "binding": "node_executor"},
        },
        {
            "event_id": "x:3", "execution_point": "phase_graph.node.end",
            "payload": {
                "node_id": "phase.perceive.observe", "visit_index": 1,
                "elapsed_ms": 5, "dispatch": "next",
                "inputs": {}, "outputs": {"manifest": {"digest": "sha256:abc", "items": []}},
                "outcome": "success", "error": "",
            },
        },
        {
            "event_id": "x:4", "execution_point": "phase_graph.node.start",
            "payload": {"node_id": "think.reason.complete", "visit_index": 1, "binding": "node_executor"},
        },
        {
            "event_id": "x:5", "execution_point": "phase_graph.node.end",
            "payload": {
                "node_id": "think.reason.complete", "visit_index": 1,
                "elapsed_ms": 1000, "dispatch": "terminal",
                "inputs": {"forked_tools": "x"}, "outputs": {
                    "response": {
                        "model": "qwen3.7-plus",
                        "finish_reason": "tool_calls",
                        "tool_calls": [{"name": "runCommand", "arguments": {"command": "ls"}}],
                    },
                },
                "outcome": "success", "error": "",
            },
        },
        {"event_id": "x:6", "execution_point": "runtime.reducer.apply",
         "payload": {"method": "apply_error", "phase": "start", "outcome": None}},
        {"event_id": "x:7", "execution_point": "runtime.reducer.apply",
         "payload": {"method": "apply_error", "phase": "end", "outcome": "success"}},
        {"event_id": "x:8", "execution_point": "runtime.reducer.apply",
         "payload": {"method": "apply_stop", "phase": "end", "outcome": "success"}},
        {
            "event_id": "x:9", "execution_point": "kernel.run.stop",
            "payload": {"run_id": run_id, "outcome": "failure"},
        },
    ]
    spine.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
    return run_dir


def test_build_debug_graph_extracts_nodes_reducer_llm_and_root_cause(fake_run_dir: Path) -> None:
    """Pure-function contract: nodes + reducer_sequence + llm_calls + anomalies."""
    from lca.infrastructure.cli.commands.observation.debug_graph import _load_events

    run_id = "run_test_debug_graph"
    events = _load_events(run_id)
    report = build_debug_graph(events)

    assert report["node_count"] == 2
    node_ids = {n["node_id"] for n in report["nodes"]}
    assert "phase.perceive.observe" in node_ids
    assert "think.reason.complete" in node_ids
    # tool_call 进了 node
    reason_node = next(n for n in report["nodes"] if n["node_id"] == "think.reason.complete")
    assert reason_node["tool_calls"][0]["name"] == "runCommand"
    assert reason_node["tool_calls"][0]["arguments"]["command"] == "ls"
    # reducer 序列含 apply_error / apply_stop
    methods = [r["method"] for r in report["reducer_sequence"]]
    assert "apply_error" in methods
    assert "apply_stop" in methods
    # AGENTS.md §3 C12: apply_stop precedes apply_terminal_outcome as a
    # normal teardown path; it must NOT be flagged by name. Anomalies are
    # now driven by outcome=failure only.
    joined = " | ".join(report["anomalies"])
    assert "apply_stop" not in joined
    assert "kernel.run.stop outcome=failure" in joined


def test_debug_graph_cli_top_level_alias_human_output(fake_run_dir: Path) -> None:
    """``lca-ops debug-graph <run_id>`` top-level alias prints human report."""
    runner = CliRunner()
    result = runner.invoke(app, ["debug-graph", "run_test_debug_graph"])
    assert result.exit_code == 0, result.output
    out = result.output
    assert "=== debug-graph run_id=run_test_debug_graph ===" in out
    assert "─── graph skeleton ───" in out
    assert "─── reducer apply_* sequence ───" in out
    assert "· apply_stop" in out  # apply_stop is normal teardown (C12), not flagged
    assert "tool_call: runCommand(command='ls')" in out  # tool call rendered
    assert "─── root-cause markers ───" in out


def test_debug_graph_cli_json_mode_emits_structured_report(fake_run_dir: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["debug-graph", "run_test_debug_graph", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["run_id"] == "run_test_debug_graph"
    assert payload["node_count"] == 2
    assert any(r["method"] == "apply_stop" for r in payload["reducer_sequence"])
    assert "kernel.run.stop outcome=failure" in payload["anomalies"]


def test_debug_graph_observation_subcommand_also_registered(fake_run_dir: Path) -> None:
    """Same impl reachable via ``lca-ops observation debug-graph``."""
    runner = CliRunner()
    result = runner.invoke(app, ["observation", "debug-graph", "run_test_debug_graph"])
    assert result.exit_code == 0, result.output
    assert "graph skeleton" in result.output


def test_debug_graph_missing_run_reports_error(fake_run_dir: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["debug-graph", "run_does_not_exist"])
    # CliRunner sometimes swallows typer.Exit; rely on stderr message instead
    assert "no spine at" in (result.output + (result.stderr or ""))
