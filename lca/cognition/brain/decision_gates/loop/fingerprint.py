"""Shared fingerprint helpers for loop detection gates (ADR-0191 R7).

Pure fingerprint computations live in
``lca.contracts.models.core.execution.fingerprint``; this module re-exports
them for cognition callers and keeps the observation-view fingerprint that
only gates consume.
"""

from __future__ import annotations

from lca.contracts.models.core.execution.control_turn import ControlTurnView
from lca.contracts.models.core.execution.fingerprint import (
    fingerprint_payload,
    normalize_for_fingerprint,
    tool_call_fingerprint,
    view_tool_fingerprint,
)


def view_observation_fingerprint(turn: ControlTurnView) -> str | None:
    payload = normalize_for_fingerprint(
        {
            "success": turn.observation_success,
            "payload": turn.observation_payload,
            "error": turn.observation_error,
        }
    )
    if payload is None:
        return None
    return fingerprint_payload(payload)


__all__ = [
    "fingerprint_payload",
    "normalize_for_fingerprint",
    "tool_call_fingerprint",
    "view_observation_fingerprint",
    "view_tool_fingerprint",
]
