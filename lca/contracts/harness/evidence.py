"""Auditable evidence entries for retrieval-backed Agent answers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    source_ref: str
    snippet: str
    relevance: float
    title: str = ""

    def __post_init__(self) -> None:
        if not self.evidence_id.strip() or not self.source_ref.strip():
            raise ValueError("evidence identity must not be empty")
        if not self.snippet.strip():
            raise ValueError("evidence snippet must not be empty")
        if not 0.0 <= self.relevance <= 1.0:
            raise ValueError("evidence relevance must be between 0 and 1")


__all__ = ["Evidence"]
