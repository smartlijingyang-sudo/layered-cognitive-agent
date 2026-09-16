"""``debug-run`` [5/8] error_ref must name the failure a failed run recorded.

``_extract_failure`` derived the error only from
``manifest.extra.doctor_report.hops.H6.error``, ``manifest.session_error``,
``extra.flush_errors``, and the ledger's ``exception.caught`` EP. A
deterministic tool failure populates none of those: ``H6`` records only
``{"ok": false, "outcome": "failed", "detail": ...}``, nothing raised so
there is no ``exception.caught``, and the run's real error sits in
``step.tool_result.record`` as ``error`` + ``failure_kind``. The result
was ``[5/8] error_ref (none)``, ``[6/8]`` empty and ``[7/8] (none)`` on
``run_eed09c1df112``, a run the manifest marks failed — the same "did it
fail?" question ``explain`` answers, answered differently.

Ledger records below are byte-shaped like the real ones.
"""

from __future__ import annotations

import json
from pathlib import Path

from lca.plugins.tools.diagnostics.debug.run import (
    DebugRunToolAdapter,
    _extract_failure,
    _run_failed,
    _suggest_action_from_failure_kind,
)

RUN_ID = "run_bbbbbbbbbbbb"


def _record(ep: str, seq: int, payload: dict[str, object]) -> dict[str, object]:
    return {
        "category": f"spine.{ep}",
        "channel": "fact",
        "event_id": f"{RUN_ID}:{seq}",
        "execution_point": ep,
        "payload": payload,
        "ts": "2026-09-16T16:28:34.984690+00:00",
    }


def _write_run(
    root: Path,
    records: list[dict[str, object]],
    *,
    session_status: str,
    h6_error: str = "",
) -> None:
    run_dir = root / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / f"{RUN_ID}.spine.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    manifest = {
        "schema": "lca.run_manifest/1",
        "run_id": RUN_ID,
        "session_status": session_status,
        "session_error": "",
        "extra": {
            "doctor_report": {
                "status": session_status,
                "hops": {"H6": {"ok": session_status != "failed", "error": h6_error}},
            },
            "flush_errors": [],
        },
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


_TOOL_FAILURE = _record(
    "step.tool_result.record",
    482,
    {
        "outcome": "failure",
        "failure_kind": "validation",
        "tool_name": "import_skill",
        "error": "SKILL.md frontmatter missing 'references'",
    },
)
_STOP_FAILURE = _record("kernel.run.stop", 1040, {"outcome": "failure"})
_STOP_SUCCESS = _record("kernel.run.stop", 900, {"outcome": "success"})


def test_failed_run_names_the_ledger_error(tmp_path: Path) -> None:
    """The regression: manifest carries no error, the ledger does."""
    _write_run(tmp_path, [_TOOL_FAILURE, _STOP_FAILURE], session_status="failed")
    report = DebugRunToolAdapter.from_locator_root(str(tmp_path)).debug_run(RUN_ID)

    assert report.error_message is not None
    assert "tool=import_skill" in report.error_message
    assert "failure_kind=validation" in report.error_message
    assert "seq=482" in report.error_message
    assert "SKILL.md frontmatter missing 'references'" in report.error_message
    assert report.error_type == "validation"
    assert report.suggested_action is not None
    assert "not retryable" in report.suggested_action


def test_manifest_error_still_wins_over_the_ledger(tmp_path: Path) -> None:
    """Existing behavior is preserved when the doctor hop captured an error."""
    _write_run(
        tmp_path,
        [_TOOL_FAILURE, _STOP_FAILURE],
        session_status="failed",
        h6_error="node=think.main error_kind=internal",
    )
    report = DebugRunToolAdapter.from_locator_root(str(tmp_path)).debug_run(RUN_ID)
    assert report.error_message == "node=think.main error_kind=internal"


def test_successful_run_with_a_recovered_tool_failure_stays_clean(tmp_path: Path) -> None:
    """Negative control: no invented error label on a run that completed."""
    _write_run(tmp_path, [_TOOL_FAILURE, _STOP_SUCCESS], session_status="completed")
    report = DebugRunToolAdapter.from_locator_root(str(tmp_path)).debug_run(RUN_ID)
    assert report.error_message is None
    assert report.error_type is None
    assert report.suggested_action is None
    assert not _run_failed(
        json.loads((tmp_path / "runs" / RUN_ID / "manifest.json").read_text(encoding="utf-8")),
        [_TOOL_FAILURE, _STOP_SUCCESS],
    )


def test_failed_run_without_any_carrier_says_what_was_searched(tmp_path: Path) -> None:
    """``[5/8]`` may never read ``(none)`` on a run the manifest marks failed."""
    topology_only = [
        _record("phase_graph.node.start", 1, {"node_id": "perceive.main"}),
        _record("phase_graph.node.end", 2, {"node_id": "perceive.main", "outcome": "success"}),
    ]
    _write_run(tmp_path, topology_only, session_status="failed")
    report = DebugRunToolAdapter.from_locator_root(str(tmp_path)).debug_run(RUN_ID)
    assert report.error_message is not None
    assert "no error carrier found" in report.error_message
    assert "step.tool_result.record" in report.error_message
    error_ref_line = next(
        line for line in report.render_text().splitlines() if "[5/8] error_ref" in line
    )
    assert "(none)" not in error_ref_line


def test_exception_caught_carrier_is_read(tmp_path: Path) -> None:
    caught = _record(
        "exception.caught",
        77,
        {"error_type": "ValueError", "node_id": "think.main", "message": "bad port"},
    )
    _write_run(tmp_path, [caught, _STOP_FAILURE], session_status="failed")
    report = DebugRunToolAdapter.from_locator_root(str(tmp_path)).debug_run(RUN_ID)
    assert report.error_message is not None
    assert "node=think.main" in report.error_message
    assert "bad port" in report.error_message
    assert report.failure_node_id == "think.main"


def test_failed_graph_node_carrier_is_read(tmp_path: Path) -> None:
    node_end = _record(
        "phase_graph.node.end",
        31,
        {"node_id": "act.dispatch", "outcome": "failure", "error": "boom", "dispatch": "terminal"},
    )
    _write_run(tmp_path, [node_end, _STOP_FAILURE], session_status="failed")
    _, error_message, _ = _extract_failure(
        json.loads((tmp_path / "runs" / RUN_ID / "manifest.json").read_text(encoding="utf-8")),
        [node_end, _STOP_FAILURE],
    )
    assert error_message is not None
    assert "node=act.dispatch" in error_message
    assert "boom" in error_message


def test_stack_frames_section_explains_its_own_emptiness(tmp_path: Path) -> None:
    _write_run(tmp_path, [_TOOL_FAILURE, _STOP_FAILURE], session_status="failed")
    report = DebugRunToolAdapter.from_locator_root(str(tmp_path)).debug_run(RUN_ID)
    assert report.stack_frames == ()
    rendered = report.render_text()
    assert "no exception.caught" in rendered
    assert "journal exceptions" in rendered


def test_suggested_action_follows_the_closed_failure_kind_set() -> None:
    assert "retryable" in (_suggest_action_from_failure_kind("transient", None) or "")
    for kind in ("validation", "execution", "tool_wire"):
        action = _suggest_action_from_failure_kind(kind, None)
        assert action is not None
        assert "not retryable" in action
    assert _suggest_action_from_failure_kind(None, None) is None


def test_debug_run_agrees_with_explain_on_whether_the_run_failed(tmp_path: Path) -> None:
    """The two surfaces must not disagree about the run's outcome."""
    from lca.infrastructure.cli.commands.kernel._shared import run_failure_evidence
    from lca.plugins.tools.diagnostics.failure.explainer import FailureExplainer

    for status, records in (
        ("failed", [_TOOL_FAILURE, _STOP_FAILURE]),
        ("completed", [_TOOL_FAILURE, _STOP_SUCCESS]),
    ):
        _write_run(tmp_path, records, session_status=status)
        ledger = tmp_path / "runs" / RUN_ID / f"{RUN_ID}.spine.jsonl"
        debug_report = DebugRunToolAdapter.from_locator_root(str(tmp_path)).debug_run(RUN_ID)
        explain_report = FailureExplainer(ledger).explain_failure(run_id=RUN_ID)
        debug_says_failed = debug_report.error_message is not None
        explain_says_failed = bool(explain_report["causal_chain"])
        if status == "failed":
            assert debug_says_failed, "debug-run must name the failure"
            assert explain_says_failed, "explain must project the failure"
        else:
            assert not debug_says_failed, "debug-run must not invent an error"
            assert run_failure_evidence(ledger) is None
