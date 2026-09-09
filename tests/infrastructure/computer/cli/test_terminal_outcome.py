"""Terminal outcome SSOT tests."""

from __future__ import annotations

from lca.contracts.atoms.semantic.cli_diagnostic import is_cli_diagnostic_output
from lca.cognition.convergence.payload import is_substantive_stdout
from lca.infrastructure.computer.cli.outcome import resolve_terminal_success


def test_officecli_unknown_subcommand_is_not_success() -> None:
    stdout = (
        "'read' was not matched. Did you mean one of the following?\n"
        "raw\n\nUsage:\n  officecli [command] [options]\n"
    )
    assert not resolve_terminal_success(exit_code=0, stdout=stdout, stderr="")
    assert is_cli_diagnostic_output(stdout)
    assert not is_substantive_stdout(stdout)


def test_json_success_overrides_exit_code() -> None:
    assert resolve_terminal_success(
        exit_code=2,
        stdout='{"success": true, "data": {}}',
        stderr="",
    )


def test_json_failure_overrides_exit_code() -> None:
    assert not resolve_terminal_success(
        exit_code=0,
        stdout='{"success": false, "error": {"code": "not_found"}}',
        stderr="",
    )


def test_real_stdout_still_success_with_exit_zero() -> None:
    stdout = "文档结构概览\n" + ("章节内容\n" * 10)
    assert resolve_terminal_success(exit_code=0, stdout=stdout, stderr="")
    assert is_substantive_stdout(stdout)
