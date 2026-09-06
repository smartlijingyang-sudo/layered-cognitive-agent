"""Typed run diagnostic — ADR-0122.

Every phase failure that reaches the run boundary carries a
:class:`RunDiagnostic` so the diagnostic surface is preserved end-to-end:
PhaseTransaction → StopDecision.failure → reducer → TerminalOutcome →
doctor_report / UI. The previous design crammed failure detail into
``StopDecision.final_output`` (a string slot for the successful answer),
then the reducer wrote a fixed Chinese fallback when ``state.last_error``
was empty — losing the original exception type, stack, and attempt history.

This module owns:

- :class:`StackFrame` — one line of a captured traceback
- :class:`PhaseAttemptSummary` — typed view of one attempted run
- :class:`RunDiagnostic` — full failure record carried through the seam

Capture helpers (:func:`capture_run_diagnostic`) live in the harness layer
so runtime primitives never import pydantic-free types themselves.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = [
    "PhaseAttemptSummary",
    "RunDiagnostic",
    "StackFrame",
]


@dataclass(frozen=True, slots=True)
class StackFrame:
    """One frame of a captured traceback (ADR-0122)."""

    filename: str
    lineno: int
    name: str
    source_line: str | None = None


@dataclass(frozen=True, slots=True)
class PhaseAttemptSummary:
    """Typed summary of one phase-attempt failure (replaces dict[str, int|str])."""

    attempt: int
    category: str  # PhaseErrorCategory value
    error_type: str
    message: str | None = None


@dataclass(frozen=True, slots=True)
class RunDiagnostic:
    """End-to-end failure record preserved across the run boundary.

    StopDecision.failure, reducer.last_error, TerminalOutcome.error_ref and
    doctor_report.H6.error_ref all carry this same object so any of those
    surfaces can reconstruct the original exception.
    """

    run_id: str
    trace_id: str
    phase: str  # SemanticPhase value
    node_id: str
    error_type: str
    message: str
    stack: tuple[StackFrame, ...]
    causation: tuple[str, ...]
    attempts: tuple[PhaseAttemptSummary, ...]
    suggested_action: str | None = None
    extra: tuple[tuple[str, Any], ...] = ()

    def top_frames(self, limit: int = 8) -> tuple[StackFrame, ...]:
        """Return at most ``limit`` top frames for compact rendering."""
        return self.stack[:limit]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dict (used by Journal / Doctor)."""
        return {
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "phase": self.phase,
            "node_id": self.node_id,
            "error_type": self.error_type,
            "message": self.message,
            "stack": [
                {
                    "filename": f.filename,
                    "lineno": f.lineno,
                    "name": f.name,
                    "source_line": f.source_line,
                }
                for f in self.stack
            ],
            "causation": list(self.causation),
            "attempts": [
                {
                    "attempt": a.attempt,
                    "category": a.category,
                    "error_type": a.error_type,
                    "message": a.message,
                }
                for a in self.attempts
            ],
            "suggested_action": self.suggested_action,
            "extra": dict(self.extra),
        }
