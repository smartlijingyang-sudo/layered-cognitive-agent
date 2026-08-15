"""lca-cli command results follow LobeHub local-file-shell, not execFile throw."""

from __future__ import annotations

from pathlib import Path

_CLI = Path("packages/lca-cli/src/tools")


def test_non_zero_exit_is_completed_observation() -> None:
    result = (_CLI / "shell-result.ts").read_text(encoding="utf-8")
    assert "exitCode" in result
    assert "completedCommand" in result
    assert "fromExecError" in result
    assert "success: true" in result
    assert "command timed out" in result


def test_run_command_uses_shared_timeout() -> None:
    run = (_CLI / "run-command.ts").read_text(encoding="utf-8")
    timeout = (_CLI / "timeout.ts").read_text(encoding="utf-8")
    assert "resolveTimeoutMs" in run
    assert "timeout_s" in timeout
    assert "fromExecError" in run
    assert "Command failed" not in run


def test_dispatcher_does_not_inline_execfile() -> None:
    index = (_CLI / "index.ts").read_text(encoding="utf-8")
    assert "from './run-command.js'" in index
    assert "execFileAsync" not in index
