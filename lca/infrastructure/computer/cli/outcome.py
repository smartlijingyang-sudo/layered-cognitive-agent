"""Terminal command outcome SSOT — transport facts → semantic success."""

from __future__ import annotations

from lca.contracts.atoms.semantic.cli_diagnostic import is_cli_diagnostic_output
from lca.infrastructure.computer.cli.json import cli_json_success


def resolve_terminal_success(*, exit_code: int, stdout: str, stderr: str) -> bool:
    """Classify whether a terminal command semantically succeeded."""
    json_ok = cli_json_success(stdout)
    if json_ok is not None:
        return json_ok
    combined = f"{stdout or ''}\n{stderr or ''}".strip()
    if is_cli_diagnostic_output(combined):
        return False
    return exit_code == 0


__all__ = ["resolve_terminal_success"]
