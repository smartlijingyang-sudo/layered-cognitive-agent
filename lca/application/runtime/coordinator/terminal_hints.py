"""RunSession.status → wire status enum mapping.

The native AgentGateway exposes a 6-value status enum on `resume_complete`
and on the data of `agent_runtime_end`. This module maps the existing
LCA `RunSession.status` (an internal enum) to that wire contract.
"""

from __future__ import annotations

from typing import Literal

TerminalHint = Literal[
    "running",
    "waiting_input",
    "waiting_confirmation",
    "completed",
    "error",
    "interrupted",
]


_TERMINAL_STATUSES = {
    "done",
    "error",
    "interrupted",
    "waiting_for_human",
    "completed",
    "waiting_input",
    "awaiting_human",
    "input-required",
}


def is_stream_terminal_status(status: str) -> bool:
    """True iff the status ends the WS stream for the current operation id.

    spec §4.2: `waiting_for_human` is stream-terminal but state-resumable.
    The same op id's stream is closed; a new op id (or a new resume call)
    carries the next phase. Matches native `STREAM_END_STATUSES` set
    in `AgentRuntimeCoordinator.ts:30-34`.
    """
    return status in _TERMINAL_STATUSES


def resolve_live_terminal_hint(session: object) -> TerminalHint:
    """Map RunSession.status to the wire 6-value enum."""
    status = getattr(session, "status", None)
    # session.error set on any terminal-like state overrides to "error"
    if getattr(session, "error", None):
        return "error"
    if status in ("done", "completed"):
        return "completed"
    if status in ("waiting_input", "waiting_for_human", "awaiting_human", "input-required"):
        return "waiting_input"
    if status == "interrupted":
        return "interrupted"
    if status == "error":
        return "error"
    return "running"


__all__ = ("TerminalHint", "is_stream_terminal_status", "resolve_live_terminal_hint")
