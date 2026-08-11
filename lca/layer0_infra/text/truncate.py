"""Canonical text truncation — single implementation, configurable suffix.

All truncate helpers across the codebase (policy, reasoner, projector,
sandbox/computer observations) delegate here to eliminate duplication.
"""

from __future__ import annotations

from typing import Final

ELLIPSIS: Final[str] = "\u2026"
ASCII_ELLIPSIS: Final[str] = "..."


def truncate_text(text: str, max_len: int, *, suffix: str = ELLIPSIS) -> str:
    """Truncate *text* to *max_len* characters, appending *suffix* if exceeded.

    The returned string length is ``max_len + len(suffix)`` when truncation
    occurs — callers that need a hard total-length cap should pre-subtract
    ``len(suffix)`` from *max_len*.
    """
    if len(text) <= max_len:
        return text
    return text[:max_len] + suffix
