"""Run live observe contracts (ADR-0100).

Command/observation split: ``POST /runs`` changes system state;
``GET /runs/{id}/live`` is a canvas projection only. Journal fold is SSOT
for terminal facts; SSE ``done`` must not invent failures while still running.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LiveTerminalHint:
    """Carrier/session fallback when the journal tail closes without ``done``."""

    status: str
    error: str = ""

    def as_tuple(self) -> tuple[str, str]:
        return self.status, self.error


__all__ = ["LiveTerminalHint"]
