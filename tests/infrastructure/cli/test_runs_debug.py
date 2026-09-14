"""Tests for ``lca-ops runs debug`` orchestrator (5-layer projection).

Pins the contract that every layer emits a payload, JSON mode defaults to
json output, the graph layer defaults to layer=graph, and missing spine
returns exit code 1 with a spine_missing payload.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from lca.infrastructure.cli.cli.cli import app


@pytest.fixture
def run_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    run_id = "run_test_runs_debug"
    rd = tmp_path / "traces" / "runs" / run_id
    rd.mkdir(parents=True)
    spine = rd / f"{run_id}.spine.jsonl"
    rows = [
        {"execution_point": "kernel.run.start", "channel": "fact", "span_id": "s1",
         "parent_span_id": None, "sequence": 1, "epoch": 1, "causality_id": "c1",
         "outcome": None, "when": "2026-09-14T00:00:00+00:00",
         "when_corrected": "2026-09-14T00:00:00+00:00",
         "prev_event_hash": None, "run_id": run_id, "step_id": None, "payload": {}},
        {"execution_point": "kernel.run.stop", "channel": "fact", "span_id": "s2",
         "parent_span_id": "s1", "sequence": 2, "epoch": 1, "causality_id": "c2",
         "outcome": "failure", "when": "2026-09-14T00:00:01+00:00",
         "when_corrected": "2026-09-14T00:00:01+00:00",
         "prev_event_hash": None, "run_id": run_id, "step_id": None,
         "payload": {"outcome": "failure", "error": ""}},
    ]
    spine.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return rd


def test_runs_debug_default_layer_graph_json(run_dir: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["runs", "debug", "run_test_runs_debug"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["layer"] == "graph"
    assert "nodes" in payload
    assert "node_count" in payload


def test_runs_debug_summary_layer(run_dir: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["runs", "debug", "run_test_runs_debug",
                                 "--layer", "summary", "--output", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["layer"] == "summary"
    assert payload["total_events"] == 2
    assert payload["terminal_outcome"] == "failure"
    assert payload["anomalies_present"] is True
    assert "next_layer" in payload["hint"]


def test_runs_debug_events_layer(run_dir: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["runs", "debug", "run_test_runs_debug",
                                 "--layer", "events", "--output", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["layer"] == "events"
    assert len(payload["rows"]) == 2
    assert payload["rows"][0]["execution_point"] == "kernel.run.start"


def test_runs_debug_explain_layer(run_dir: Path) -> None:
    """The fixture only has a terminal kernel.run.stop=failure; no
    phase_graph.node.end carries outcome=failure. The explain layer must
    NOT promote kernel.run.stop into first_failed (it is the terminal
    verdict, not the root cause). Instead it surfaces a 'reducer-driven
    terminal' summary and points the agent at graph layer reducer_sequence.
    """
    runner = CliRunner()
    result = runner.invoke(app, ["runs", "debug", "run_test_runs_debug",
                                 "--layer", "explain", "--output", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["layer"] == "explain"
    assert payload["root_cause_present"] is False
    assert payload["terminal_outcome"] == "failure"
    assert "reducer" in payload["hint"]


def test_runs_debug_explain_layer_with_node_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When a phase_graph.node.end carries outcome=failure, explain must
    surface it as first_failed (not kernel.run.stop)."""
    monkeypatch.chdir(tmp_path)
    run_id = "run_test_explain_node_fail"
    rd = tmp_path / "traces" / "runs" / run_id
    rd.mkdir(parents=True)
    rows = [
        {"execution_point": "phase_graph.node.end", "channel": "fact",
         "span_id": "s1", "parent_span_id": None, "sequence": 1, "epoch": 1,
         "causality_id": "c1", "outcome": None, "when": "2026-09-14T00:00:01+00:00",
         "when_corrected": "2026-09-14T00:00:01+00:00", "prev_event_hash": None,
         "run_id": run_id, "step_id": None,
         "payload": {"node_id": "think.reason.complete", "outcome": "failure",
                     "error": "llm timeout", "ts": "2026-09-14T00:00:01+00:00"}},
        {"execution_point": "kernel.run.stop", "channel": "fact",
         "span_id": "s2", "parent_span_id": "s1", "sequence": 2, "epoch": 1,
         "causality_id": "c2", "outcome": "failure",
         "when": "2026-09-14T00:00:02+00:00",
         "when_corrected": "2026-09-14T00:00:02+00:00", "prev_event_hash": None,
         "run_id": run_id, "step_id": None,
         "payload": {"outcome": "failure", "error": ""}},
    ]
    (rd / f"{run_id}.spine.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows), encoding="utf-8"
    )
    runner = CliRunner()
    result = runner.invoke(app, ["runs", "debug", run_id,
                                 "--layer", "explain", "--output", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["root_cause_present"] is True
    assert payload["first_failed"]["node_id"] == "think.reason.complete"
    assert payload["first_failed"]["error"] == "llm timeout"
    assert "events" in payload["hint"]


def test_runs_debug_human_output(run_dir: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["runs", "debug", "run_test_runs_debug",
                                 "--layer", "summary", "--output", "human"])
    assert result.exit_code == 0, result.output
    assert "=== runs debug layer=summary ===" in result.output
    assert "total_events" in result.output


def test_runs_debug_missing_spine_payload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["runs", "debug", "run_does_not_exist", "--output", "json"])
    combined = result.output + (result.stderr or "")
    assert "spine_missing" in combined
    assert "run_does_not_exist" in combined


def test_runs_debug_unknown_layer_rejected(run_dir: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["runs", "debug", "run_test_runs_debug",
                                 "--layer", "bogus"])
    combined = result.output + (result.stderr or "")
    assert "unknown layer" in combined
    assert "bogus" in combined
