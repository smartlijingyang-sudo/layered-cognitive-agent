"""Tests for graph trajectory extraction in debug-run (ADR-0122 extension).

Locks in the ``[9/9] graph.trajectory`` section: phase_graph.node.start/end
and phase_graph.subgraph.enter/exit events from the spine are extracted
and rendered in the diagnostic report.
"""

from __future__ import annotations

import json
from pathlib import Path

from lca.plugins.tools.diagnostics.debug.run import (
    DebugRunToolAdapter,
    _extract_graph_trajectory,
)


def test_extract_graph_trajectory_empty() -> None:
    events: list[dict] = []
    assert _extract_graph_trajectory(events) == ()


def test_extract_graph_trajectory_node_lifecycle() -> None:
    events = [
        {
            "execution_point": "phase_graph.node.start",
            "payload": {"node_id": "shortcut"},
        },
        {
            "execution_point": "phase_graph.node.end",
            "payload": {"node_id": "shortcut", "outcome": "success"},
        },
        {
            "execution_point": "phase_graph.node.start",
            "payload": {"node_id": "route"},
        },
        {
            "execution_point": "phase_graph.node.end",
            "payload": {
                "node_id": "route",
                "outcome": "failure",
                "exception_message": "boom",
            },
        },
    ]
    result = _extract_graph_trajectory(events)
    assert len(result) == 4
    assert result[0] == {"kind": "node", "event": "start", "node_id": "shortcut"}
    assert result[1] == {
        "kind": "node",
        "event": "end",
        "node_id": "shortcut",
        "outcome": "success",
        "error": "",
    }
    assert result[3]["outcome"] == "failure"
    assert result[3]["error"] == "boom"


def test_extract_graph_trajectory_subgraph_lifecycle() -> None:
    events = [
        {
            "execution_point": "phase_graph.subgraph.enter",
            "payload": {
                "plan_ref": "think-v2",
                "entry_node": "reason",
                "depth": 1,
            },
        },
        {
            "execution_point": "phase_graph.subgraph.exit",
            "payload": {
                "plan_ref": "think-v2",
                "entry_node": "reason",
                "outcome": "success",
                "depth": 1,
                "error": "",
            },
        },
    ]
    result = _extract_graph_trajectory(events)
    assert len(result) == 2
    assert result[0]["kind"] == "subgraph"
    assert result[0]["event"] == "enter"
    assert result[0]["plan_ref"] == "think-v2"
    assert result[1]["kind"] == "subgraph"
    assert result[1]["outcome"] == "success"


def _write_run_with_graph_events(traces_root: Path, run_id: str) -> None:
    run_dir = traces_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": "lca/run_manifest/1",
        "run_id": run_id,
        "plan_ref": "test-plan",
        "extra": {"doctor_report": {"status": "completed"}},
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest))
    spine_events = [
        {"execution_point": "kernel.run.start", "run_seq": 1},
        {
            "execution_point": "phase_graph.node.start",
            "payload": {"node_id": "shortcut"},
            "run_seq": 2,
        },
        {
            "execution_point": "phase_graph.node.end",
            "payload": {"node_id": "shortcut", "outcome": "success"},
            "run_seq": 3,
        },
        {
            "execution_point": "phase_graph.subgraph.enter",
            "payload": {
                "plan_ref": "think-v2",
                "entry_node": "reason",
                "depth": 1,
            },
            "run_seq": 4,
        },
        {
            "execution_point": "phase_graph.node.start",
            "payload": {"node_id": "reason"},
            "run_seq": 5,
        },
        {
            "execution_point": "phase_graph.node.end",
            "payload": {"node_id": "reason", "outcome": "success"},
            "run_seq": 6,
        },
        {
            "execution_point": "phase_graph.subgraph.exit",
            "payload": {
                "plan_ref": "think-v2",
                "entry_node": "reason",
                "outcome": "success",
                "depth": 1,
                "error": "",
            },
            "run_seq": 7,
        },
        {"execution_point": "kernel.run.stop", "run_seq": 8},
    ]
    (run_dir / f"{run_id}.spine.jsonl").write_text("\n".join(json.dumps(e) for e in spine_events))


def test_debug_run_report_includes_graph_trajectory(tmp_path: Path) -> None:
    run_id = "run_graph_001"
    _write_run_with_graph_events(tmp_path, run_id)
    adapter = DebugRunToolAdapter.from_locator_root(str(tmp_path))
    report = adapter.debug_run(run_id)

    assert len(report.graph_trajectory) == 6
    text = report.render_text()
    assert "[9/9] graph.trajectory" in text
    # 4 node events (2 start + 2 end) + 2 subgraph events (1 enter + 1 exit)
    assert "nodes=4" in text
    assert "subgraphs=2" in text
    assert "trajectory" in text
    assert "subgraph" in text


def test_debug_run_report_no_graph_events(tmp_path: Path) -> None:
    run_id = "run_graph_002"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    manifest = {"run_id": run_id, "extra": {"doctor_report": {"status": "ok"}}}
    (run_dir / "manifest.json").write_text(json.dumps(manifest))
    (run_dir / f"{run_id}.spine.jsonl").write_text(
        json.dumps({"execution_point": "kernel.run.start", "run_seq": 1})
    )
    adapter = DebugRunToolAdapter.from_locator_root(str(tmp_path))
    report = adapter.debug_run(run_id)
    assert report.graph_trajectory == ()
    assert "(no phase_graph events in spine)" in report.render_text()


def test_debug_run_json_roundtrip_includes_graph_trajectory(tmp_path: Path) -> None:
    run_id = "run_graph_003"
    _write_run_with_graph_events(tmp_path, run_id)
    adapter = DebugRunToolAdapter.from_locator_root(str(tmp_path))
    report = adapter.debug_run(run_id)
    encoded = json.dumps(report.to_dict())
    decoded = json.loads(encoded)
    assert len(decoded["graph_trajectory"]) == 6
    assert decoded["graph_trajectory"][0]["kind"] == "node"
