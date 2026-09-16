"""Test that journal exceptions no longer scans spine (Task 1.10 / G-11)."""
from __future__ import annotations

import json
from pathlib import Path


def _make_journal_app():
    import typer
    app = typer.Typer()
    journal_app = typer.Typer()
    from lca.infrastructure.cli.commands.journal import exceptions as journal_exceptions
    journal_exceptions.register(journal_app)
    app.add_typer(journal_app, name="journal")
    return app


def test_no_fallback_when_sidecar_missing():
    """Without sidecar, journal exceptions returns count=0 regardless of spine content."""
    from typer.testing import CliRunner
    runner = CliRunner()
    result = runner.invoke(_make_journal_app(), ["journal", "exceptions", "run_3383288d63e7", "--json"])
    assert result.exit_code == 0, f"CLI failed: {getattr(result, 'stderr', result.output)}"
    payload = json.loads(result.stdout)
    assert payload["source"] == "no_sidecar", (
        f"source must be 'no_sidecar' when sidecar missing; got {payload['source']!r}"
    )
    assert payload["count"] == 0
    assert payload["records"] == []


def test_fallback_function_removed_from_source():
    """The _iter_spine_exception_records helper is gone from the module."""
    from lca.infrastructure.cli.commands.journal import exceptions as journal_exceptions
    assert not hasattr(journal_exceptions, "_iter_spine_exception_records"), (
        "_iter_spine_exception_records should be deleted per G-11"
    )


def test_spine_fallback_string_removed_from_source():
    """Source code no longer contains 'source = spine_fallback' branch marker."""
    source = Path("lca/infrastructure/cli/commands/journal/exceptions.py").read_text()
    assert 'source = "spine_fallback"' not in source, (
        "source='spine_fallback' branch must be gone per G-11"
    )
