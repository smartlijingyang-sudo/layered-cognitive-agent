"""Unified CLI output mode for observation surface.

Two modes: `human` (multi-line, color-free text) and `json` (single dict).
`json` is the agent-friendly default; `human` is explicit for operators.

Each command still owns its own rendering — this module only centralizes the
flag parsing + dispatch so every command presents the same surface and
agent callers can declare one uniform expectation.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from enum import StrEnum
from typing import Any

import typer


class OutputMode(StrEnum):
    HUMAN = "human"
    JSON = "json"


def emit(
    mode: OutputMode,
    payload: dict[str, Any],
    *,
    human_renderer: Callable[[dict[str, Any]], str],
) -> None:
    """Dispatch payload to the right output stream."""
    if mode is OutputMode.HUMAN:
        typer.echo(human_renderer(payload))
        return
    typer.echo(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
    )


def output_option(default: OutputMode) -> typer.Option:
    """Standard `--output` flag with stable help text."""
    return typer.Option(
        default,
        "--output",
        help="Output mode. `json` is agent-friendly (default).",
    )


__all__ = ["OutputMode", "emit", "output_option"]
