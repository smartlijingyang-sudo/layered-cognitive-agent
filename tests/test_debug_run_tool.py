"""``lca-ops debug-run <run_id>`` — ADR-0122 one-shot diagnostic.

The previous debug workflow required catting several files plus running
``ps`` + ``/proc/<pid>/fd/1`` to find kernel stdout. This test locks in
the new ``DebugRunToolAdapter`` so a future regression that breaks the
debug surface (e.g. silently dropping the journal path or status field)
gets caught.
"""

from __future__ import annotations

import json
from pathlib import Path

from lca.plugins.tools.diagnostics.debug_run import DebugRunToolAdapter


def _write_run_dir(
    traces_root: Path, run_id: str, *, status: str = "failed", error: str = "boom"
) -> None:
    run_dir = traces_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": "lca.run_manifest/1",
        "run_id": run_id,
        "terminal_event_seq": 12,
        "extra": {
            "doctor_report": {
                "status": status,
                "hops": {
                    "H6": {
                        "ok": status != "completed",
                        "error": error,
                        "attempts": [],
                    }
                },
            }
        },
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest))
    # Minimal journal: seq=1, 2, 3, 10, 11, 12 (3,4,5,6,7,8,9 dropped).
    envelopes = [
        {
            "run_seq": 1,
            "descriptor": {"type": "AgentRunStarted"},
            "data": {"attributes": {"payload": {}}},
        },
        {
            "run_seq": 2,
            "descriptor": {"type": "ContextCompacted"},
            "data": {"attributes": {"payload": {}}},
        },
        {
            "run_seq": 3,
            "descriptor": {"type": "ContextManifested"},
            "data": {"attributes": {"payload": {}}},
        },
        {
            "run_seq": 10,
            "descriptor": {"type": "RuntimeObserved"},
            "data": {
                "plugin": "stop",
                "operation": "phase.fact",
                "attributes": {
                    "payload": {
                        "node": "stop.main",
                        "result_kind": "stop_decision",
                        "failure": {
                            "node_id": "think.main",
                            "reason": "error",
                            "final_output": "think.main step after 1 attempt(s).",
                            "attempts": [
                                {
                                    "attempt": 1,
                                    "category": "permanent",
                                    "error_type": "RuntimeError",
                                }
                            ],
                        },
                    }
                },
            },
        },
        {"run_seq": 11, "descriptor": {"type": "RuntimeObserved"}, "data": {"attributes": {}}},
        {"run_seq": 12, "descriptor": {"type": "AgentRunFinished"}, "data": {"attributes": {}}},
    ]
    (run_dir / "journal.jsonl").write_text("\n".join(json.dumps(e) for e in envelopes))
    spine_events = [
        {"execution_point": "kernel.run.start", "run_id": run_id},
        {"execution_point": "exception.caught", "run_id": run_id},
        {"execution_point": "kernel.run.stop", "run_id": run_id},
    ]
    (run_dir / "events.jsonl").write_text("\n".join(json.dumps(e) for e in spine_events))


def test_debug_run_extracts_8_section(tmp_path: Path) -> None:
    """Smoke-test: every section of the report renders deterministically."""
    run_id = "run_test_001"
    _write_run_dir(tmp_path, run_id)
    adapter = DebugRunToolAdapter.from_locator_root(str(tmp_path))
    report = adapter.debug_run(run_id)

    # [1] manifest summary reaches doctor_report.status
    assert report.manifest_summary["extra"]["doctor_report"]["status"] == "failed"
    assert "manifest.json" in report.manifest_path

    # [2] journal counts every event; missing seqs surface for review
    assert report.journal_event_count == 6
    assert report.journal_missing_seqs == (4, 5, 6, 7, 8, 9)
    assert report.spine_event_count == 3
    assert "events.jsonl" in report.spine_events_path
    assert report.spine_execution_points[-1] == "kernel.run.stop"
    assert "spine.events" in report.render_text()

    # [4] phase.cursor: last meaningful node before stop is recovered
    assert report.phase_cursor in {"stop.main", "stop.main (failed)"}

    # [5] error_ref: the failure blob contains typed detail
    assert report.error_message is not None
    assert report.failure_node_id == "think.main"

    # [8] replay command is the canonical no-LLM invocation
    assert report.replay_command == f"lca-ops replay {run_id} --no-llm"

    text = report.render_text()
    for marker in ("[1/8]", "[2/8]", "[3/8]", "[4/8]", "[5/8]", "[6/8]", "[7/8]", "[8/8]"):
        assert marker in text


def test_debug_run_json_output_serialisable(tmp_path: Path) -> None:
    """``--json`` mode emits a dict-shaped report (consumable by tooling)."""
    run_id = "run_test_002"
    _write_run_dir(tmp_path, run_id, status="completed", error="")
    adapter = DebugRunToolAdapter.from_locator_root(str(tmp_path))
    report = adapter.debug_run(run_id)
    d = report.to_dict()
    # Round-trip through JSON to ensure no dataclass leaks through.
    encoded = json.dumps(d)
    decoded = json.loads(encoded)
    assert decoded["run_id"] == run_id
    assert decoded["journal_event_count"] == 6
    # ``manifest_summary`` carries the doctor_report.status verbatim.
    assert decoded["manifest_summary"]["extra"]["doctor_report"]["status"] == "completed"


def test_debug_run_no_kernel_log_does_not_crash(tmp_path: Path) -> None:
    """Missing kernel.log is allowed (older runs have no per-run log yet)."""
    run_id = "run_test_003"
    _write_run_dir(tmp_path, run_id)
    adapter = DebugRunToolAdapter.from_locator_root(str(tmp_path))
    report = adapter.debug_run(run_id)
    assert report.kernel_log_tail == ""
