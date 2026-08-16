"""Migration flags for the session spine (spec §B.9)."""

from __future__ import annotations

import os
from typing import Literal

SpineMode = Literal["off", "shadow", "authoritative", "legacy_removed"]

_VALID: frozenset[str] = frozenset({"off", "shadow", "authoritative", "legacy_removed"})


def session_spine_mode() -> SpineMode:
    raw = os.environ.get("LCA_SESSION_SPINE", "off").strip().lower()
    if raw not in _VALID:
        return "off"
    return raw  # type: ignore[return-value]


MIGRATION_FLAGS: dict[str, SpineMode] = {
    "session_spine": session_spine_mode(),
}
