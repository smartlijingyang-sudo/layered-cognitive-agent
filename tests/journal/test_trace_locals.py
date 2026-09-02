"""Tests for ``lca-ops journal trace [--locals] [--source]`` (Task 9.3).

The CLI reads the spine ``events.jsonl`` (one ``EventRecord`` per line,
JSON-encoded by ``lca.infrastructure.observability.spine.sinks.file_sink``)
and prints a human-readable table. The brief requires:

- The default view shows ``seq / execution_point / channel / outcome /
  when / source``.
- ``--source`` is implied by ``--locals``; ``--locals`` adds the
  ``next_frame`` and ``locals`` columns.
- I17-compliant events have ``source_location`` in their payload; the
  CLI surfaces file:line + function.
- The CLI is read-only; misconfigured ``events.jsonl`` (no
  ``source_location``) produces ``"-"`` rather than crashing.

These tests build a synthetic ``events.jsonl`` via the spine
``FileSink`` so we exercise the same write path the real spine uses.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from lca.infrastructure.cli.cli import app
from lca.infrastructure.observability.spine.event_record import (
    EventRecord,
    Outcome,
)
from lca.infrastructure.observability.spine.sinks.file_sink import FileSink

runner = CliRunner()


def _make_record(
    *,
    sequence: int,
    execution_point: str,
    payload: dict,
    outcome: Outcome | None = "success",
    when_iso: str = "2026-09-01T00:00:00+00:00",
) -> EventRecord:
    """Build a minimal :class:`EventRecord` for a single trace row.

    Only the fields the CLI reads (``execution_point``, ``channel``,
    ``span_id``, ``parent_span_id``, ``sequence``, ``run_id``,
    ``payload``, ``when``, ``outcome``) are populated; the rest take
    their dataclass defaults because the CLI never inspects them.
    """
    from datetime import datetime

    return EventRecord(
        execution_point=execution_point,
        channel="fact",
        span_id=f"span-{sequence:04d}",
        parent_span_id=None,
        sequence=sequence,
        epoch=1,
        causality_id=f"causality-{sequence:04d}",
        outcome=outcome,
        when=datetime.fromisoformat(when_iso),
        when_corrected=datetime.fromisoformat(when_iso),
        prev_event_hash=None,
        run_id="run_test",
        step_id=None,
        payload=payload,
        phase="live",
        reason=None,
    )


def _write_events_jsonl(run_dir: Path, records: list[EventRecord]) -> Path:
    """Append one ``EventRecord`` per line via ``FileSink``. Returns the path."""
    sink = FileSink(run_dir, run_id="run_test", file_name="events.jsonl")
    for record in records:
        sink.write(record)
    sink.close()
    return run_dir / "events.jsonl"


@pytest.fixture
def traces_root(tmp_path: Path) -> Path:
    """Build a traces root with one run directory containing ``events.jsonl``."""
    root = tmp_path / "traces"
    run_dir = root / "runs" / "run_test"
    run_dir.mkdir(parents=True)

    records = [
        _make_record(
            sequence=1,
            execution_point="brain.perceive.start",
            payload={
                "source_location": {
                    "file": "brain/perceive.py",
                    "line": 42,
                    "function": "perceive",
                },
                "call_frames": [
                    {
                        "file": "agent/loop.py",
                        "line": 100,
                        "function": "step",
                    }
                ],
                "locals_snapshot": {
                    "pre_call": {
                        "locals": {"input": "<prompt 64 chars>"},
                        "ctx": {"model": "'gpt-4o'"},
                    }
                },
            },
            when_iso="2026-09-01T00:00:01+00:00",
        ),
        _make_record(
            sequence=2,
            execution_point="brain.think.start",
            payload={
                "source_location": {
                    "file": "brain/think.py",
                    "line": 17,
                    "function": "think",
                },
                "call_frames": [],
                "locals_snapshot": {"pre_call": {}},
            },
            when_iso="2026-09-01T00:00:02+00:00",
        ),
        _make_record(
            sequence=3,
            execution_point="brain.think.end",
            payload={"return_value": "ok"},
            outcome="success",
            when_iso="2026-09-01T00:00:03+00:00",
        ),
        _make_record(
            sequence=4,
            execution_point="body.tool.execute.start",
            payload={
                "source_location": {
                    "file": "tools/sandbox.py",
                    "line": 88,
                    "function": "invoke",
                },
                "call_frames": [
                    {
                        "file": "body/executor.py",
                        "line": 12,
                        "function": "execute",
                    }
                ],
                "locals_snapshot": {
                    "pre_call": {
                        "locals": {"name": "'bash'", "args": "{'cmd': 'ls'}"},
                        "ctx": {"OPENAI_API_KEY": "'***'"},
                    }
                },
            },
            when_iso="2026-09-01T00:00:04+00:00",
        ),
    ]
    _write_events_jsonl(run_dir, records)
    return root


# ── default table view ──────────────────────────────────────────────


def test_default_table_includes_source_column(traces_root: Path) -> None:
    """The default table includes seq / point / channel / outcome / when / source."""
    result = runner.invoke(
        app,
        ["journal", "trace", "run_test", "--traces-root", str(traces_root)],
    )
    assert result.exit_code == 0, result.stderr
    assert "seq" in result.stdout
    assert "execution_point" in result.stdout
    assert "source" in result.stdout
    # The first record is brain.perceive.start with source_location
    # pointing at brain/perceive.py:42 — both must appear.
    assert "brain/perceive.py:42" in result.stdout
    assert "perceive" in result.stdout
    # Events without source_location (brain.think.end) show "-".
    assert "brain.think.end" in result.stdout
    # The trace summary footer counts rendered rows.
    assert "events rendered" in result.stdout


def test_default_table_does_not_show_locals(traces_root: Path) -> None:
    """The default table does NOT show next_frame / locals columns."""
    result = runner.invoke(
        app,
        ["journal", "trace", "run_test", "--traces-root", str(traces_root)],
    )
    assert result.exit_code == 0
    # The ``locals`` column header MUST NOT appear unless ``--locals``
    # was passed.
    assert "locals" not in result.stdout.split("events rendered")[0].splitlines()[0]
    assert "next_frame" not in result.stdout


# ── --locals flag ───────────────────────────────────────────────────


def test_locals_flag_adds_locals_columns(traces_root: Path) -> None:
    """``--locals`` adds the next_frame + locals columns and shows locals."""
    result = runner.invoke(
        app,
        [
            "journal",
            "trace",
            "run_test",
            "--locals",
            "--traces-root",
            str(traces_root),
        ],
    )
    assert result.exit_code == 0, result.stderr
    assert "next_frame" in result.stdout
    assert "locals" in result.stdout
    # First event has ``call_frames[0]`` at agent/loop.py:100 step.
    assert "agent/loop.py:100" in result.stdout
    # locals_snapshot.pre_call['locals']['input'] = "<prompt 64 chars>"
    assert "input=" in result.stdout


def test_locals_implies_source(traces_root: Path) -> None:
    """``--locals`` implies ``--source`` so the source column is also visible."""
    result = runner.invoke(
        app,
        [
            "journal",
            "trace",
            "run_test",
            "--locals",
            "--traces-root",
            str(traces_root),
        ],
    )
    assert result.exit_code == 0
    assert "brain/perceive.py:42" in result.stdout


def test_source_flag_keeps_locals_column_off(traces_root: Path) -> None:
    """``--source`` alone does NOT add the locals column."""
    result = runner.invoke(
        app,
        [
            "journal",
            "trace",
            "run_test",
            "--source",
            "--traces-root",
            str(traces_root),
        ],
    )
    assert result.exit_code == 0
    assert "brain/perceive.py:42" in result.stdout
    # locals column header MUST NOT appear without --locals.
    header_line = result.stdout.splitlines()[0]
    assert "locals" not in header_line


def test_redacted_locals_value_surfaces_in_table(traces_root: Path) -> None:
    """Redacted locals values (``***``) survive the table renderer unchanged."""
    result = runner.invoke(
        app,
        [
            "journal",
            "trace",
            "run_test",
            "--locals",
            "--traces-root",
            str(traces_root),
        ],
    )
    assert result.exit_code == 0
    # SourceAttacher collapses OPENAI_API_KEY value to "***". The CLI
    # just renders the value verbatim, so the redaction sentinel must
    # show up in the locals column.
    assert "OPENAI_API_KEY='***'" in result.stdout or "OPENAI_API_KEY=***" in result.stdout


# ── JSON output ────────────────────────────────────────────────────


def test_json_output_carries_source_and_locals(traces_root: Path) -> None:
    """``--json --locals`` emits structured rows including source_location."""
    result = runner.invoke(
        app,
        [
            "journal",
            "trace",
            "run_test",
            "--json",
            "--locals",
            "--traces-root",
            str(traces_root),
        ],
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema"] == "lca.journal_trace/1"
    assert payload["run_id"] == "run_test"
    assert payload["with_locals"] is True
    assert payload["with_source"] is True
    assert payload["rendered"] == 4
    rows = payload["rows"]
    # First row has source_location pointing at brain/perceive.py.
    assert rows[0]["source_location"]["file"] == "brain/perceive.py"
    assert rows[0]["source_location"]["line"] == 42
    assert rows[0]["source_location"]["function"] == "perceive"
    assert rows[0]["next_frame"] == "agent/loop.py:100 (step)"
    # brain.think.end has no source_location — JSON encodes ``None``.
    assert rows[2]["source_location"] is None
    assert rows[2]["locals_snapshot"] is None


def test_json_output_default_skips_locals_columns(traces_root: Path) -> None:
    """Default JSON output keeps ``with_locals=False`` but still emits source."""
    result = runner.invoke(
        app,
        [
            "journal",
            "trace",
            "run_test",
            "--json",
            "--traces-root",
            str(traces_root),
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["with_locals"] is False
    assert payload["with_source"] is False
    # source_location column is still present (default view).
    assert payload["rows"][0]["source_location"]["file"] == "brain/perceive.py"


# ── error handling ─────────────────────────────────────────────────


def test_missing_run_dir_friendly_error(tmp_path: Path) -> None:
    """Missing run directory yields a friendly error and exit code 1."""
    root = tmp_path / "traces"
    root.mkdir()
    result = runner.invoke(
        app,
        ["journal", "trace", "missing", "--traces-root", str(root)],
    )
    assert result.exit_code == 1
    assert "run directory not found" in result.stderr or "not found" in result.stderr


def test_missing_events_jsonl_friendly_error(tmp_path: Path) -> None:
    """Existing run dir without ``events.jsonl`` yields a friendly error."""
    root = tmp_path / "traces"
    run_dir = root / "runs" / "noevents"
    run_dir.mkdir(parents=True)
    result = runner.invoke(
        app,
        ["journal", "trace", "noevents", "--traces-root", str(root)],
    )
    assert result.exit_code == 1
    assert "events.jsonl not found" in result.stderr


# ── edge cases ─────────────────────────────────────────────────────


def test_event_without_source_location_renders_dash(traces_root: Path) -> None:
    """``*.end`` events lacking ``source_location`` render as ``-`` in source column."""
    result = runner.invoke(
        app,
        ["journal", "trace", "run_test", "--traces-root", str(traces_root)],
    )
    assert result.exit_code == 0
    # brain.think.end has no source_location. Find the row and assert
    # the source column is "-".
    lines = result.stdout.splitlines()
    # Find the row for brain.think.end.
    target = next(line for line in lines if "brain.think.end" in line)
    # The source column is the last column on this row; the row
    # formatter pads it. We assert the column begins with "-".
    assert " - " in target or target.rstrip().endswith("-")


def test_limit_flag_caps_rows(tmp_path: Path) -> None:
    """``--limit 2`` returns the first 2 rows only."""
    root = tmp_path / "traces"
    run_dir = root / "runs" / "limited"
    run_dir.mkdir(parents=True)
    records = [
        _make_record(
            sequence=i,
            execution_point=("brain.perceive.start" if i % 2 else "brain.think.start"),
            payload={
                "source_location": {
                    "file": f"f{i}.py",
                    "line": i,
                    "function": f"g{i}",
                },
                "call_frames": [],
                "locals_snapshot": {"pre_call": {}},
            },
        )
        for i in range(1, 6)
    ]
    _write_events_jsonl(run_dir, records)

    result = runner.invoke(
        app,
        [
            "journal",
            "trace",
            "limited",
            "--limit",
            "2",
            "--traces-root",
            str(root),
        ],
    )
    assert result.exit_code == 0
    # Only the first two rows are rendered; rows 3-5 must not appear.
    assert "f1.py" in result.stdout
    assert "f2.py" in result.stdout
    assert "f3.py" not in result.stdout
    assert "f5.py" not in result.stdout
    # The footer reports the rendered row count.
    assert "2 events rendered" in result.stdout


def test_skips_malformed_jsonl_lines(tmp_path: Path) -> None:
    """Malformed JSONL lines are skipped (counted as ``skipped``)."""
    root = tmp_path / "traces"
    run_dir = root / "runs" / "malformed"
    run_dir.mkdir(parents=True)
    records = [
        _make_record(
            sequence=1,
            execution_point="brain.perceive.start",
            payload={
                "source_location": {
                    "file": "f.py",
                    "line": 1,
                    "function": "g",
                },
                "call_frames": [],
                "locals_snapshot": {"pre_call": {}},
            },
        )
    ]
    events_path = _write_events_jsonl(run_dir, records)
    # Append a malformed line.
    with events_path.open("a", encoding="utf-8") as fh:
        fh.write("not-json\n")
    # And a blank line.
    with events_path.open("a", encoding="utf-8") as fh:
        fh.write("\n")

    result = runner.invoke(
        app,
        [
            "journal",
            "trace",
            "malformed",
            "--traces-root",
            str(root),
        ],
    )
    assert result.exit_code == 0
    # Blank lines are silently skipped (no count). The malformed JSON
    # line is the only ``skipped`` entry; total reports the lines we
    # read past blank ones (1 valid record + 1 malformed = 2 total).
    assert "1/2 events rendered" in result.stdout
    assert "1 skipped" in result.stdout


# ── module surface ─────────────────────────────────────────────────


def test_journal_trace_register_is_callable() -> None:
    """``journal_trace.register`` is a callable that accepts a Typer group."""
    import typer

    from lca.infrastructure.cli.commands import journal_trace

    group = typer.Typer()
    journal_trace.register(group)
    # The command should be wired on the group.
    runner_local = CliRunner()
    result = runner_local.invoke(group, ["--help"])
    assert result.exit_code == 0
    assert "trace" in result.stdout


def test_journal_trace_module_export() -> None:
    """``journal_trace`` exposes ``register`` as its public surface."""
    import lca.infrastructure.cli.commands.journal_trace as module

    assert "register" in module.__all__


# ── argument-less mode (latest run) ──────────────────────────────────


def test_no_run_id_picks_latest_via_pointer(traces_root: Path, monkeypatch) -> None:
    """Omitting ``run_id`` reads ``traces/latest.json`` and renders that run.

    The CliRunner changes cwd to a temp dir, so we monkeypatch the
    default traces root and write the atomic pointer at that root.
    """
    pointer = traces_root / "latest.json"
    pointer.write_text('{"run_id": "run_test", "kind": "run_pointer"}', encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "journal",
            "trace",
            "--traces-root",
            str(traces_root),
        ],
    )
    assert result.exit_code == 0, result.stderr
    # The rendered tree/table should include the source column for the
    # first event (proves it read run_test, not a missing run).
    assert "brain/perceive.py" in result.stdout


def test_no_run_id_picks_mtime_latest_when_pointer_missing(tmp_path: Path, monkeypatch) -> None:
    """Without ``traces/latest.json`` we fall back to mtime order.

    Two run directories under ``traces/runs/``; the second (newer) must
    be picked automatically when no run_id is given.
    """
    root = tmp_path / "traces"
    older = root / "runs" / "run_old"
    newer = root / "runs" / "run_new"
    older.mkdir(parents=True)
    newer.mkdir(parents=True)

    # Older run: one harmless event.
    sink_old = FileSink(older, run_id="run_old", file_name="events.jsonl")
    sink_old.write(
        _make_record(
            sequence=1,
            execution_point="brain.perceive.start",
            payload={"source_location": {"file": "old.py", "line": 1, "function": "f"}},
            when_iso="2026-09-01T00:00:00+00:00",
        )
    )
    sink_old.close()
    # Touch the older directory earlier than the newer one.
    import os

    os.utime(older, (1_000_000, 1_000_000))

    # Newer run: identifiable event we can grep for.
    sink_new = FileSink(newer, run_id="run_new", file_name="events.jsonl")
    sink_new.write(
        _make_record(
            sequence=1,
            execution_point="brain.perceive.start",
            payload={"source_location": {"file": "new.py", "line": 99, "function": "g"}},
            when_iso="2026-09-01T00:00:00+00:00",
        )
    )
    sink_new.close()
    os.utime(newer, (2_000_000, 2_000_000))

    result = runner.invoke(
        app,
        ["journal", "trace", "--traces-root", str(root)],
    )
    assert result.exit_code == 0, result.stderr
    # Newer run wins; the older run's marker must be missing.
    assert "new.py" in result.stdout
    assert "old.py" not in result.stdout


def test_no_run_id_with_no_runs_errors(tmp_path: Path) -> None:
    """Empty ``traces/runs/`` and no pointer: friendly exit code 1."""
    root = tmp_path / "traces"
    root.mkdir()
    result = runner.invoke(
        app,
        ["journal", "trace", "--traces-root", str(root)],
    )
    assert result.exit_code == 1
    assert "no runs found" in result.stderr or "no runs" in result.stderr


def test_no_run_id_with_pointer_but_missing_run_dir(tmp_path: Path) -> None:
    """Pointer references a missing run directory → mtime fallback (empty → error).

    If the pointer is stale (run directory removed), the resolver falls
    back to mtime order. With no runs present the user gets the same
    friendly error as the empty case.
    """
    root = tmp_path / "traces"
    root.mkdir()
    (root / "latest.json").write_text(
        '{"run_id": "run_missing", "kind": "run_pointer"}', encoding="utf-8"
    )
    result = runner.invoke(
        app,
        ["journal", "trace", "--traces-root", str(root)],
    )
    assert result.exit_code == 1


def test_explicit_run_id_still_works(traces_root: Path) -> None:
    """Backwards compatibility: explicit ``run_id`` argument unchanged."""
    result = runner.invoke(
        app,
        [
            "journal",
            "trace",
            "run_test",
            "--traces-root",
            str(traces_root),
        ],
    )
    assert result.exit_code == 0, result.stderr
    assert "brain/perceive.py" in result.stdout
