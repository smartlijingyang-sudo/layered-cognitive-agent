"""Tests for ``lca-ops typecheck``."""

from __future__ import annotations

from typer.testing import CliRunner

from lca.infrastructure.cli.cli.cli import app
from lca.infrastructure.cli.commands.ops.typecheck import (
    TypeDiagnostic,
    _filter_focus,
    _parse_mypy,
    _parse_pyright,
)


def test_typecheck_help_lists_focus() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["typecheck", "--help"])
    assert result.exit_code == 0
    assert "--focus" in result.stdout
    assert "--json" in result.stdout
    assert "callable" in result.stdout


def test_parse_mypy_and_callable_focus() -> None:
    raw = (
        'lca/agent/team_handle.py:149: error: "object" not callable  [operator]\n'
        "lca/foo.py:1: error: Unsupported operand types for + (\"int\" and \"str\")  [operator]\n"
    )
    diagnostics = _parse_mypy(raw)
    assert len(diagnostics) == 2
    filtered = _filter_focus(diagnostics, "callable")
    assert len(filtered) == 1
    assert filtered[0].path == "lca/agent/team_handle.py"


def test_parse_pyright_call_issue() -> None:
    raw = (
        "  /home/x/lca/plugins/prompts/sections.py:649:28 - error: "
        'Object of type "object" is not callable (reportCallIssue)\n'
    )
    diagnostics = _parse_pyright(raw)
    assert len(diagnostics) == 1
    assert diagnostics[0].code == "reportCallIssue"
    filtered = _filter_focus(diagnostics, "callable")
    assert len(filtered) == 1


def test_lazy_import_focus_keeps_attr_defined() -> None:
    diagnostics = [
        TypeDiagnostic(
            tool="mypy",
            path="lca/x.py",
            line=1,
            column=None,
            message='"object" has no attribute "flush"',
            code="attr-defined",
        )
    ]
    filtered = _filter_focus(diagnostics, "lazy-import")
    assert len(filtered) == 1
