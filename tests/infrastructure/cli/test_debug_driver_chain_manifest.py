"""``debug-driver-chain`` must say when it could not filter by run window.

The command reconstructs a run's node-execution chain from kernel stderr and
narrows it to the run's time window using ``traces/runs/<run_id>/manifest.json``.
When that manifest is missing or unreadable the command still prints a chain —
it just cannot narrow it. A corrupt manifest therefore has to be announced, or
an operator reading ``debug-run`` output cannot tell a filtered chain from an
unfiltered one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from lca.infrastructure.cli.commands.runs import driver_debug

_LOG_LINE = "2026-09-15 10:00:00,001 phase_graph.driver.start run_id={run_id}\n"


def _prepare(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    manifest: str | None,
) -> Path:
    stderr_file = tmp_path / "kernel.stderr.log"
    stderr_file.write_text(_LOG_LINE.format(run_id="r1"), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "traces" / "runs" / "r1"
    run_dir.mkdir(parents=True)
    if manifest is not None:
        (run_dir / "manifest.json").write_text(manifest, encoding="utf-8")
    monkeypatch.setattr(driver_debug, "find_stderr_for_run", lambda _run_id: stderr_file)
    return stderr_file


def _report(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    return json.loads(capsys.readouterr().out)


def test_corrupt_manifest_is_announced_on_stderr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepare(monkeypatch, tmp_path, manifest="{ not json")

    driver_debug.cmd_debug_driver_chain("r1", json_mode=True)

    captured = capsys.readouterr()
    assert "no run-window filtering applied" in captured.err
    assert "JSONDecodeError" in captured.err
    report = json.loads(captured.out)
    assert report["started_at"] is None
    assert report["entry_count"] == 1


def test_no_warning_when_manifest_is_readable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepare(monkeypatch, tmp_path, manifest=json.dumps({"started_at": 1, "closed_at": 2}))

    driver_debug.cmd_debug_driver_chain("r1", json_mode=True)

    captured = capsys.readouterr()
    assert "no run-window filtering applied" not in captured.err
    assert json.loads(captured.out)["started_at"] == 1


def test_missing_manifest_stays_silent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No manifest at all is the documented "take everything" case."""
    _prepare(monkeypatch, tmp_path, manifest=None)

    driver_debug.cmd_debug_driver_chain("r1", json_mode=True)

    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out)["started_at"] is None
