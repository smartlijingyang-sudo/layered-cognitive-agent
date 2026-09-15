"""``audit_ssot_field_drift`` must not report a partial scan as a clean one.

The audit walks ``traces/runs/<id>/<id>.spine.jsonl`` line by line. A spine is
written by a live kernel and can be truncated or hold a non-JSON line; both the
per-line parse and the enclosing scan used to swallow the error and keep going,
so a run whose log was half-unreadable came back with zero findings — the
optimistic answer for a tool whose whole job is finding drift.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_ssot_field_drift import _scan_run


def _write_spine(run_dir: Path, lines: list[str]) -> Path:
    run_dir.mkdir(parents=True)
    (run_dir / f"{run_dir.name}.spine.jsonl").write_text("\n".join(lines), encoding="utf-8")
    return run_dir


def _fold_line(seq: int, kind: str, objective: str) -> str:
    return json.dumps(
        {
            "execution_point": "phase.think.fold",
            "sequence": seq,
            "payload": {"objective_kind": kind, "objective": objective},
        }
    )


def test_unreadable_line_is_reported(tmp_path: Path) -> None:
    run_dir = _write_spine(
        tmp_path / "run-bad",
        [
            _fold_line(1, "user_text", "book a flight"),
            "{not json",
            _fold_line(2, "user_text", "hi"),
        ],
    )

    findings = _scan_run(run_dir)

    unreadable = findings["spine.unreadable_line"]
    assert [item["line"] for item in unreadable] == [2]
    assert unreadable[0]["run_id"] == "run-bad"


def test_scan_abort_is_reported(tmp_path: Path) -> None:
    """A record shape the scanner cannot process must surface, not truncate."""
    run_dir = _write_spine(
        tmp_path / "run-weird",
        [
            _fold_line(1, "user_text", "book a flight"),
            json.dumps(["execution_point", "phase.think.fold"]),
        ],
    )

    findings = _scan_run(run_dir)

    aborted = findings["spine.scan_aborted"]
    assert [item["error"] for item in aborted] == ["AttributeError"]
    assert aborted[0]["run_id"] == "run-weird"


def test_clean_run_still_produces_no_findings(tmp_path: Path) -> None:
    run_dir = _write_spine(
        tmp_path / "run-clean",
        [_fold_line(1, "user_text", "book a flight"), _fold_line(2, "agent_role", "researcher")],
    )

    findings = _scan_run(run_dir)

    assert dict(findings) == {}


def test_model_name_in_objective_is_still_a_drift(tmp_path: Path) -> None:
    run_dir = _write_spine(
        tmp_path / "run-drift",
        [_fold_line(1, "user_text", "qwen3.7-plus")],
    )

    findings = _scan_run(run_dir)

    hits = findings["phase.think.fold.objective=user_text/模型名"]
    assert [item["value"] for item in hits] == ["qwen3.7-plus"]
