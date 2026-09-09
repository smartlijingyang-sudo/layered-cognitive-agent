"""Pure CLI diagnostic/help detection — shared by Body outcome and Convergence fold."""

from __future__ import annotations

import re

_CLI_DIAGNOSTIC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"was not matched", re.IGNORECASE),
    re.compile(r"Unrecognized command or argument", re.IGNORECASE),
    re.compile(r"Required command was not provided", re.IGNORECASE),
    re.compile(r"Did you mean one of the following", re.IGNORECASE),
    re.compile(r"^Usage:\s", re.MULTILINE),
    re.compile(r"^Commands:\s", re.MULTILINE),
)


def is_cli_diagnostic_output(text: str) -> bool:
    """True when text is CLI help/rejection, not user-visible task output."""
    stripped = (text or "").strip()
    if not stripped:
        return False
    return any(pattern.search(stripped) for pattern in _CLI_DIAGNOSTIC_PATTERNS)


__all__ = ["is_cli_diagnostic_output"]
