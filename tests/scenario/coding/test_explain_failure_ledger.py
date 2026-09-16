"""``lca-ops explain <run_id>`` must read the ledger that carries the failure.

Two defects made a genuinely failed run report "no failure found" with
exit code 0:

1. ``explain`` resolved ``traces/runs/<id>/journal.json`` — a
   ``lca.journal/3.1`` *document* (the folded step-tree projection).
   Read line-by-line as a ledger it yields zero events, so the explainer
   always saw an empty stream even though
   ``<run_id>.spine.jsonl`` next to it held ``kernel.run.stop
   outcome=failure``.
2. ``_event_from_payload``'s spine v3 branch read ``scope`` /
   ``sequence`` / ``when`` / top-level ``run_id``. The spine writer
   emits none of those: the run id and ledger sequence live in
   ``event_id`` (``"<run_id>:<seq>"``) and ``payload``, and the time in
   ``ts`` as ISO-8601. Every event parsed with ``run_id=""``, so
   ``_select(run_id=...)`` dropped the whole ledger.

The fixtures below are byte-shaped like the real records in
``traces/runs/run_eed09c1df112/run_eed09c1df112.spine.jsonl``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from lca.infrastructure.cli.cli.cli import app
from lca.infrastructure.cli.commands.kernel._shared import (
    resolve_event_ledger_path,
    run_failure_evidence,
    spine_terminal_outcome,
)
from lca.plugins.tools.diagnostics.failure.explainer import FailureExplainer
from lca.plugins.tools.diagnostics.helpers._helpers import (
    _event_from_payload,
    _inspector_events,
    _load_inspector_from_jsonl,
)

RUN_ID = "run_aaaaaaaaaaaa"


@pytest.fixture
def real_sys_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Undo ``tests/conftest.py::_block_kernel_sys_exit`` for exit-code asserts.

    That autouse fixture stubs ``sys.exit`` so kernel-dispose tests keep
    running; typer routes ``typer.Exit`` through ``sys.exit``, so without
    this the CLI's non-zero exit is unobservable.
    """

    def _exit(code: int = 0) -> None:
        raise SystemExit(code)

    monkeypatch.setattr(sys, "exit", _exit)


def _spine_record(ep: str, seq: int, payload: dict[str, object]) -> dict[str, object]:
    """One record in the shape ``SpineEventRecord`` writes to the ledger."""
    return {
        "category": f"spine.{ep}",
        "causation_id": None,
        "channel": "fact",
        "event_hash": None,
        "event_id": f"{RUN_ID}:{seq}",
        "execution_point": ep,
        "payload": payload,
        "prev_event_hash": None,
        "trace_id": None,
        "ts": "2026-09-16T16:28:34.984690+00:00",
    }


def _failed_ledger() -> list[dict[str, object]]:
    return [
        _spine_record("kernel.run.start", 2, {"run_id": RUN_ID}),
        _spine_record(
            "step.tool_result.record",
            482,
            {
                "outcome": "failure",
                "failure_kind": "validation",
                "tool_name": "import_skill",
                "error": "SKILL.md frontmatter missing 'references'",
                "run_id": RUN_ID,
            },
        ),
        _spine_record(
            "kernel.run.stop",
            1040,
            {"outcome": "failure", "run_id": RUN_ID, "trace_id": "trace_a"},
        ),
    ]


def _successful_ledger() -> list[dict[str, object]]:
    return [
        _spine_record("kernel.run.start", 2, {"run_id": RUN_ID}),
        _spine_record(
            "kernel.run.stop",
            900,
            {"outcome": "success", "run_id": RUN_ID, "trace_id": "trace_a"},
        ),
    ]


def _write_run(
    root: Path,
    records: list[dict[str, object]],
    *,
    session_status: str,
    with_journal_document: bool = True,
) -> Path:
    """Lay out ``traces/runs/<id>/`` the way the carrier does."""
    run_dir = root / "traces" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    ledger = run_dir / f"{RUN_ID}.spine.jsonl"
    with ledger.open("w", encoding="utf-8") as handle:
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
                "broken_hop": "H6" if session_status == "failed" else None,
                "hops": {"H6": {"ok": session_status != "failed", "outcome": session_status}},
                "flush_errors": [],
            },
            "flush_errors": [],
        },
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    if with_journal_document:
        # Pretty-printed on purpose: a document, not a ledger. This is the
        # artifact ``resolve_journal_path`` used to hand to ``explain``.
        (run_dir / "journal.json").write_text(
            json.dumps({"schema": "lca.journal/3.1", "run_id": RUN_ID, "steps": []}, indent=2),
            encoding="utf-8",
        )
    return ledger


def test_spine_v3_record_yields_run_id_seq_and_ts() -> None:
    """The regression: real spine records carry no ``scope`` / ``sequence``."""
    stamped = _event_from_payload(_spine_record("kernel.run.stop", 1040, {"outcome": "failure"}))
    assert stamped is not None
    assert str(stamped.scope.run_id) == RUN_ID
    assert stamped.seq == 1040
    assert stamped.ts == pytest.approx(1789576114.98469)
    assert stamped.event_type == "kernel.run.stop"
    assert stamped.data["outcome"] == "failure"


def test_trace_id_falls_back_to_payload() -> None:
    stamped = _event_from_payload(
        _spine_record("kernel.run.stop", 7, {"trace_id": "trace_inner", "outcome": "failure"})
    )
    assert stamped is not None
    assert str(stamped.scope.trace_id) == "trace_inner"


def test_inspector_selects_the_whole_ledger_by_run_id(tmp_path: Path) -> None:
    """``_select(run_id=...)`` used to drop all 650 events of a real run."""
    ledger = _write_run(tmp_path, _failed_ledger(), session_status="failed")
    inspector = _load_inspector_from_jsonl(ledger)
    events = _inspector_events(inspector)
    assert len(events) == 3
    assert inspector._select(trace_id=None, run_id=RUN_ID) == tuple(events)
    assert [e.seq for e in events] == [2, 482, 1040]


def test_explain_prefers_the_ledger_over_the_journal_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``journal.json`` existing must not hide the ledger from ``explain``."""
    _write_run(tmp_path, _failed_ledger(), session_status="failed")
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["explain", RUN_ID])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["event_count"] == 3
    assert report["causal_chain"], "failed run must project a causal chain"
    # The window ends at the terminal event.
    assert report["events"][-1]["type"] == "kernel.run.stop"
    assert report["events"][-1]["data"]["outcome"] == "failure"


def test_explain_exit_zero_on_successful_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative control: a successful run must not be reported as failed."""
    _write_run(tmp_path, _successful_ledger(), session_status="completed")
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["explain", RUN_ID])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["event_count"] == 2
    assert report["causal_chain"] == []
    assert "未在所选事件中发现失败终态" in report["summary"]


def test_explain_fails_loud_when_the_ledger_cannot_explain_a_failed_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, real_sys_exit: None
) -> None:
    """A failed run whose ledger holds only graph topology must not exit 0.

    Mirrors ``run_ba9375d926c5``: 70 events, all ``phase_graph.*``, no
    ``kernel.run.stop`` and no failure carrier, while the manifest
    records ``session_status=failed``.
    """
    topology_only = [
        _spine_record("phase_graph.node.start", 1, {"node_id": "perceive.main"}),
        _spine_record(
            "phase_graph.node.end", 2, {"node_id": "perceive.main", "outcome": "success"}
        ),
    ]
    _write_run(tmp_path, topology_only, session_status="failed")
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["explain", RUN_ID])
    assert result.exit_code == 1
    assert "no failure event" in result.output
    assert "manifest session_status=failed" in result.output


def test_explain_missing_ledger_names_the_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, real_sys_exit: None
) -> None:
    (tmp_path / "traces" / "runs" / RUN_ID).mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["explain", RUN_ID])
    assert result.exit_code == 1
    assert f"{RUN_ID}.spine.jsonl" in result.output


def test_resolve_event_ledger_path_ignores_the_journal_document(tmp_path: Path) -> None:
    ledger = _write_run(tmp_path, _failed_ledger(), session_status="failed")
    with pytest.MonkeyPatch.context() as monkey:
        monkey.chdir(tmp_path)
        resolved = resolve_event_ledger_path(None, RUN_ID).resolve()
    assert resolved == ledger.resolve()


def test_spine_terminal_outcome_reads_the_last_stop_event(tmp_path: Path) -> None:
    failed = _write_run(tmp_path, _failed_ledger(), session_status="failed")
    assert spine_terminal_outcome(failed) == "failure"
    assert spine_terminal_outcome(tmp_path / "missing.spine.jsonl") == "unknown"


def test_run_failure_evidence_prefers_ledger_then_manifest(tmp_path: Path) -> None:
    ledger = _write_run(tmp_path, _failed_ledger(), session_status="failed")
    assert run_failure_evidence(ledger) == "ledger kernel.run.stop outcome=failure"

    # No stop event in the ledger: the manifest still records the failure.
    topology = _write_run(
        tmp_path,
        [_spine_record("phase_graph.node.end", 2, {"node_id": "x", "outcome": "success"})],
        session_status="failed",
    )
    assert run_failure_evidence(topology) == "manifest session_status=failed"


def test_run_failure_evidence_is_none_for_a_completed_run(tmp_path: Path) -> None:
    ledger = _write_run(tmp_path, _successful_ledger(), session_status="completed")
    assert run_failure_evidence(ledger) is None


def test_explainer_reads_a_real_shaped_ledger(tmp_path: Path) -> None:
    ledger = _write_run(tmp_path, _failed_ledger(), session_status="failed")
    report = FailureExplainer(ledger).explain_failure(run_id=RUN_ID)
    assert report["event_count"] == 3
    assert report["causal_chain"] == [482]
