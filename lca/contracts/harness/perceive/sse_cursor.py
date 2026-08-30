"""High-water cursor contract for replayable SSE consumers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SseCursor:
    session_id: str
    last_seq: int = -1

    def __post_init__(self) -> None:
        if not self.session_id.strip():
            raise ValueError("SSE cursor session_id must not be empty")
        if self.last_seq < -1:
            raise ValueError("SSE cursor last_seq must be at least -1")

    def next_seq(self) -> int:
        return self.last_seq + 1

    def advance(self, seq: int) -> SseCursor:
        if seq <= self.last_seq:
            return self
        return SseCursor(self.session_id, seq)


__all__ = ["SseCursor"]
