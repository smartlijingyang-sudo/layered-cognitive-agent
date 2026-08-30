"""Which Run driver owns this execution_target."""

from __future__ import annotations

DSH_TARGET = "dsh"


def is_dsh_driver(execution_target: str) -> bool:
    return (execution_target or "").strip().lower() == DSH_TARGET
