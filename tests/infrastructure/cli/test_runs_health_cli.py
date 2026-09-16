"""Test for `lca-ops runs health <run_id>` CLI (Task 1.11)."""
from __future__ import annotations

import json
from pathlib import Path

import typer
from typer.testing import CliRunner


def _make_real_app() -> typer.Typer:
    """Build the real runs sub-app structure: `lca-ops runs <subcmd>`."""
    app = typer.Typer()
    runs_app = typer.Typer(no_args_is_help=True)
    from lca.infrastructure.cli.commands.runs import health as runs_health
    runs_health.register(runs_app)
    app.add_typer(runs_app, name="runs")
    return app


_runner = CliRunner()


def test_health_cli_runs_on_audit_run():
    """`runs health run_<id>` returns JSON with overall/by_type/conditions."""
    audit_dir = Path("traces/runs")
    if not audit_dir.exists():
        import pytest
        pytest.skip("Audit data not available")
    run_dirs = sorted([d for d in audit_dir.iterdir() if d.is_dir()])
    if not run_dirs:
        import pytest
        pytest.skip("No audit runs")
    run_id = run_dirs[0].name
    result = _runner.invoke(_make_real_app(), ["runs", "health", run_id])
    assert result.exit_code == 0, f"CLI failed: {result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "1.0"
    assert payload["run_id"] == run_id
    assert payload["overall"] in {"ok", "degraded", "failed", "unknown"}
    assert isinstance(payload["by_type"], dict)
    assert isinstance(payload["conditions"], list)
    assert len(payload["conditions"]) >= 1


def test_health_cli_missing_spine_reports_error():
    """Missing spine file reports error to stderr (typer.Exit behavior in pytest
    swallows exit_code, but stderr is preserved — test stderr)."""
    result = _runner.invoke(_make_real_app(), ["runs", "health", "run_nonexistent_abc123"])
    stderr = getattr(result, "stderr", "")
    has_error = "not found" in stderr.lower() or "error" in stderr.lower()
    assert has_error, (
        f"Missing spine should report error to stderr; got exit_code={result.exit_code}, "
        f"stdout={result.stdout!r}, stderr={stderr!r}"
    )


def test_health_cli_custom_spine_path(tmp_path):
    """--spine override works with empty spine (produces all-unknown report)."""
    spine = tmp_path / "test.spine.jsonl"
    spine.write_text("")
    result = _runner.invoke(
        _make_real_app(),
        ["runs", "health", "run_dummy", "--spine", str(spine)],
    )
    assert result.exit_code == 0, f"CLI failed: {result.stderr}"
    payload = json.loads(result.stdout)
    # Empty spine: 1 unknown condition per deriver (8 derivers × 1 = 8)
    assert payload["overall"] == "unknown"
    assert all(c["status"] == "unknown" for c in payload["conditions"])
    assert len(payload["conditions"]) == 8  # one per deriver
