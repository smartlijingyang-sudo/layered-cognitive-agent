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
    phase_graph.node.end carries outcome=failure. Explain must surface
    the reducer-driven teardown as root_cause_kind=reducer_teardown
    (not first_failed) and include the reducer method.
    """
    runner = CliRunner()
    result = runner.invoke(app, ["runs", "debug", "run_test_runs_debug",
                                 "--layer", "explain", "--output", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["layer"] == "explain"
    assert payload["root_cause_present"] is True
    assert payload["root_cause_kind"] == "reducer_teardown"
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


def test_runs_debug_spine_empty_vs_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Distinguish 'no spine file' from 'file exists but all rows corrupt'.

    Both must exit 1, but the payload must surface the right cause so
    the agent can pivot to kernel logs vs runs create receipt.
    """
    monkeypatch.chdir(tmp_path)

    rd = tmp_path / "traces" / "runs" / "run_corrupt"
    rd.mkdir(parents=True)
    (rd / "run_corrupt.spine.jsonl").write_text(
        "not json\n{also bad\n", encoding="utf-8"
    )
    runner = CliRunner()
    result = runner.invoke(app, ["runs", "debug", "run_corrupt", "--output", "json"])
    combined = result.output + (result.stderr or "")
    assert "spine_empty" in combined
    assert "spine_missing" not in combined
    assert "no parseable" in combined

    result = runner.invoke(app, ["runs", "debug", "run_absent", "--output", "json"])
    combined = result.output + (result.stderr or "")
    assert "spine_missing" in combined
    assert "spine_empty" not in combined


def test_runs_debug_graph_layer_carries_chain_effects_data_flow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Graph layer must expose edges / effects / data_flow / llm_prompts
    so an agent can answer the four business questions: chain visibility,
    per-node effects, data flow edges, and the prompt that drove an LLM.
    """
    monkeypatch.chdir(tmp_path)
    run_id = "run_test_chain"
    rd = tmp_path / "traces" / "runs" / run_id
    rd.mkdir(parents=True)
    rows = [
        {"execution_point": "kernel.run.start", "channel": "fact",
         "span_id": "s1", "parent_span_id": None, "sequence": 1, "epoch": 1,
         "causality_id": "c1", "outcome": None,
         "ts": "2026-09-14T00:00:00+00:00",
         "when_corrected": "2026-09-14T00:00:00+00:00",
         "prev_event_hash": None, "run_id": run_id, "step_id": None, "payload": {}},
        {"execution_point": "phase_graph.node.start", "channel": "control",
         "span_id": "s2", "parent_span_id": "s1", "sequence": 2, "epoch": 1,
         "causality_id": "c2", "outcome": None,
         "ts": "2026-09-14T00:00:01+00:00",
         "when_corrected": "2026-09-14T00:00:01+00:00",
         "prev_event_hash": None, "run_id": run_id, "step_id": None,
         "payload": {"node_id": "phase.perceive.observe", "visit_index": 1}},
        {"execution_point": "phase_graph.node.end", "channel": "control",
         "span_id": "s3", "parent_span_id": "s2", "sequence": 3, "epoch": 1,
         "causality_id": "c3", "outcome": "success",
         "ts": "2026-09-14T00:00:02+00:00",
         "when_corrected": "2026-09-14T00:00:02+00:00",
         "prev_event_hash": None, "run_id": run_id, "step_id": None,
         "payload": {"node_id": "phase.perceive.observe", "visit_index": 1,
                     "elapsed_ms": 1000, "dispatch": "next",
                     "inputs": {},
                     "outputs": {"manifest": {"digest": "sha256:x"}}}},
        {"execution_point": "phase_graph.edge.transit", "channel": "control",
         "span_id": "s4", "parent_span_id": "s3", "sequence": 4, "epoch": 1,
         "causality_id": "c4", "outcome": None,
         "ts": "2026-09-14T00:00:03+00:00",
         "when_corrected": "2026-09-14T00:00:03+00:00",
         "prev_event_hash": None, "run_id": run_id, "step_id": None,
         "payload": {"edge_id": "phase.perceive.observe->think.reason.complete",
                     "from_node": "phase.perceive.observe",
                     "metadata": {"when": "True"}}},
        {"execution_point": "phase_graph.node.start", "channel": "control",
         "span_id": "s5", "parent_span_id": "s4", "sequence": 5, "epoch": 1,
         "causality_id": "c5", "outcome": None,
         "ts": "2026-09-14T00:00:04+00:00",
         "when_corrected": "2026-09-14T00:00:04+00:00",
         "prev_event_hash": None, "run_id": run_id, "step_id": None,
         "payload": {"node_id": "think.reason.complete", "visit_index": 1,
                     "outputs": {"_ts_in": "2026-09-14T00:00:04+00:00"}}},
        {"execution_point": "llm.call.start", "channel": "control",
         "span_id": "s6", "parent_span_id": "s5", "sequence": 6, "epoch": 1,
         "causality_id": "c6", "outcome": None,
         "ts": "2026-09-14T00:00:04+00:00",
         "when_corrected": "2026-09-14T00:00:04+00:00",
         "prev_event_hash": None, "run_id": run_id, "step_id": None,
         "payload": {"model": "qwen3.7-plus", "stream": True}},
        {"execution_point": "llm.request.header", "channel": "control",
         "span_id": "s7", "parent_span_id": "s6", "sequence": 7, "epoch": 1,
         "causality_id": "c7", "outcome": None,
         "ts": "2026-09-14T00:00:04+00:00",
         "when_corrected": "2026-09-14T00:00:04+00:00",
         "prev_event_hash": None, "run_id": run_id, "step_id": "step-001",
         "payload": {"step_id": "step-001", "reason": "initial",
                     "messages": [{"role": "user", "content": "ping"}],
                     "tools": [{"name": "runCommand"}], "system": ""}},
        {"execution_point": "llm.call.end", "channel": "control",
         "span_id": "s8", "parent_span_id": "s7", "sequence": 8, "epoch": 1,
         "causality_id": "c8", "outcome": "success",
         "ts": "2026-09-14T00:00:05+00:00",
         "when_corrected": "2026-09-14T00:00:05+00:00",
         "prev_event_hash": None, "run_id": run_id, "step_id": None,
         "payload": {"model": "qwen3.7-plus", "latency_ms": 1000,
                     "outcome": "success"}},
        {"execution_point": "phase_graph.node.end", "channel": "control",
         "span_id": "s9", "parent_span_id": "s8", "sequence": 9, "epoch": 1,
         "causality_id": "c9", "outcome": "success",
         "ts": "2026-09-14T00:00:06+00:00",
         "when_corrected": "2026-09-14T00:00:06+00:00",
         "prev_event_hash": None, "run_id": run_id, "step_id": None,
         "payload": {"node_id": "think.reason.complete", "visit_index": 1,
                     "elapsed_ms": 2000, "dispatch": "terminal",
                     "inputs": {"manifest": "x"},
                     "outputs": {"response": {"model": "qwen3.7-plus"}}}},
        {"execution_point": "kernel.run.stop", "channel": "fact",
         "span_id": "s10", "parent_span_id": "s9", "sequence": 10, "epoch": 1,
         "causality_id": "c10", "outcome": "success",
         "ts": "2026-09-14T00:00:07+00:00",
         "when_corrected": "2026-09-14T00:00:07+00:00",
         "prev_event_hash": None, "run_id": run_id, "step_id": None,
         "payload": {"outcome": "success"}},
    ]
    (rd / f"{run_id}.spine.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows), encoding="utf-8"
    )
    runner = CliRunner()
    result = runner.invoke(app, ["runs", "debug", run_id,
                                 "--layer", "graph", "--output", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)

    assert "edges" in payload, "graph layer must surface edges"
    edges = payload["edges"]
    assert any(e.get("kind") == "edge" and e.get("from") == "phase.perceive.observe"
               and e.get("to") == "think.reason.complete" for e in edges)

    assert "data_flow" in payload, "graph layer must surface data_flow"
    flow = payload["data_flow"]
    assert any(f.get("from") == "phase.perceive.observe"
               and f.get("to") == "think.reason.complete" for f in flow), (
        f"expected data_flow edge perceive->think, got {flow}"
    )

    assert "llm_prompts" in payload, "graph layer must surface llm_prompts"
    assert payload["llm_prompts"], "llm_prompts must not be empty"
    first_prompt = payload["llm_prompts"][0]
    assert first_prompt["messages"][0]["content"] == "ping"

    nodes_by_id = {n["node_id"]: n for n in payload["nodes"]}
    think = nodes_by_id.get("think.reason.complete")
    assert think is not None
    assert any(e.get("kind") == "llm_call" for e in think["effects"]), (
        f"think.reason.complete must own its llm_call effects, got {think['effects']}"
    )
    assert any(e.get("kind") == "llm_request" for e in think["effects"]), (
        "llm.request.header must attach to the LLM-calling node"
    )


def test_runs_debug_explain_layer_includes_first_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When run fails via reducer teardown, explain must surface the
    first llm prompt so the agent can see what the LLM was asked.
    """
    monkeypatch.chdir(tmp_path)
    run_id = "run_test_explain_prompt"
    rd = tmp_path / "traces" / "runs" / run_id
    rd.mkdir(parents=True)
    rows = [
        {"execution_point": "kernel.run.start", "channel": "fact",
         "span_id": "s1", "parent_span_id": None, "sequence": 1, "epoch": 1,
         "causality_id": "c1", "outcome": None,
         "ts": "2026-09-14T00:00:00+00:00",
         "when_corrected": "2026-09-14T00:00:00+00:00",
         "prev_event_hash": None, "run_id": run_id, "step_id": None,
         "payload": {}},
        {"execution_point": "llm.request.header", "channel": "control",
         "span_id": "s2", "parent_span_id": "s1", "sequence": 2, "epoch": 1,
         "causality_id": "c2", "outcome": None,
         "ts": "2026-09-14T00:00:01+00:00",
         "when_corrected": "2026-09-14T00:00:01+00:00",
         "prev_event_hash": None, "run_id": run_id, "step_id": "step-001",
         "payload": {"step_id": "step-001", "reason": "initial",
                     "messages": [{"role": "user", "content": "ping"}],
                     "tools": [], "system": ""}},
        {"execution_point": "runtime.reducer.apply", "channel": "control",
         "span_id": "s3", "parent_span_id": "s2", "sequence": 3, "epoch": 1,
         "causality_id": "c3", "outcome": None,
         "ts": "2026-09-14T00:00:02+00:00",
         "when_corrected": "2026-09-14T00:00:02+00:00",
         "prev_event_hash": None, "run_id": run_id, "step_id": None,
         "payload": {"method": "apply_error", "phase": "start"}},
        {"execution_point": "kernel.run.stop", "channel": "fact",
         "span_id": "s4", "parent_span_id": "s3", "sequence": 4, "epoch": 1,
         "causality_id": "c4", "outcome": "failure",
         "ts": "2026-09-14T00:00:03+00:00",
         "when_corrected": "2026-09-14T00:00:03+00:00",
         "prev_event_hash": None, "run_id": run_id, "step_id": None,
         "payload": {"outcome": "failure"}},
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
    assert payload["root_cause_kind"] == "reducer_teardown"
    assert payload["reducer_method"] == "apply_error"
    assert payload["first_prompt"] is not None
    assert payload["first_prompt"]["user_message_preview"] == "ping"
    assert "llm_prompts" in payload["hint"] or "graph" in payload["hint"]
