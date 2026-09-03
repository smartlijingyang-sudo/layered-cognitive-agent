"""Verify that RunBootSnapshotRecorder writes the profile_snapshot.json file at run boot."""

from pathlib import Path
from unittest.mock import MagicMock

from lca.plugins.observability.profile_snapshot_run_boot_provider import RunBootSnapshot


def test_snapshot_recorder_writes_file(monkeypatch) -> None:
    """Mocked context; verify write() is called with correct args."""
    from lca.plugins.transport.webserver.handlers.runs.session.diagnostics import (
        RunBootSnapshotRecorder,
    )

    ctx = MagicMock()
    session = MagicMock()
    session.run_id = "test-run-123"
    session.plan_ref = "plan-hash"

    captured: dict[str, object] = {}

    def fake_write(self, **kwargs):
        captured.update(kwargs)
        captured["_outdir_path"] = kwargs["outdir"]

    monkeypatch.setattr(RunBootSnapshot, "write", fake_write)

    recorder = RunBootSnapshotRecorder(ctx=ctx)
    recorder.record(session)

    assert "run_id" in captured
    assert "plugins" in captured
    assert "capabilities" in captured
    assert "control_plan" in captured


def test_snapshot_recorder_swallows_write_errors(monkeypatch) -> None:
    """If write fails, recorder does not raise (snapshot is diagnostic only)."""
    from lca.plugins.transport.webserver.handlers.runs.session.diagnostics import (
        RunBootSnapshotRecorder,
    )

    ctx = MagicMock()
    session = MagicMock()
    session.run_id = "fail-run"
    session.plan_ref = ""

    def exploding_write(self, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(RunBootSnapshot, "write", exploding_write)

    recorder = RunBootSnapshotRecorder(ctx=ctx)
    recorder.record(session)


def test_snapshot_outdir_uses_default_when_no_locator() -> None:
    """Without run_locator capability, falls back to traces/runs/<id>."""
    from lca.plugins.transport.webserver.handlers.runs.session.diagnostics import (
        _snapshot_outdir_for,
    )

    outdir = _snapshot_outdir_for("r1", ctx=None)
    assert outdir == Path("traces/runs") / "r1"
