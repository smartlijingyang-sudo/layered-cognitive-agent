"""Restart-decision table for the kernel supervisor.

``decide_restart`` is a pure, table-driven function with no I/O — the
supervisor's decider loop feeds it ``died`` events and applies whatever
:class:`RestartDecision` it returns.
"""

from __future__ import annotations

from lca.infrastructure.cli.services.kernel.supervisor.types import (
    ProgramState,
    RestartDecision,
)

# Supervisord-aligned "clean" exit codes (0 = clean, 2 = SIGINT, 3 = SIGQUIT).
_EXIT_CLEAN = frozenset({0, 2, 3})


def decide_restart(
    exit_code: int,
    *,
    autorestart: bool,
    restart_count: int,
    startretries: int,
    user_stopped: bool,
) -> RestartDecision:
    """Pure decision function — table-driven, no I/O, easy to test.

    Rules (mirrors supervisord's expected/unexpected exit semantics):
    1. user_stopped → STOPPED (no autorestart, no matter what).
    2. clean exit + autorestart=False → STOPPED.
    3. exhausted startretries → FATAL.
    4. anything else → BACKOFF with exponential backoff.
    """
    if user_stopped:
        return RestartDecision(ProgramState.STOPPED, 0.0, "user stop")
    clean = exit_code in _EXIT_CLEAN
    if clean and not autorestart:
        return RestartDecision(ProgramState.STOPPED, 0.0, "clean exit, autorestart=false")
    if restart_count >= startretries:
        return RestartDecision(
            ProgramState.FATAL,
            0.0,
            f"exhausted startretries={startretries} after exit={exit_code}",
        )
    backoff = min(2**restart_count, 30.0)
    return RestartDecision(
        ProgramState.BACKOFF,
        backoff,
        f"retry {restart_count + 1}/{startretries} after exit={exit_code}",
    )
