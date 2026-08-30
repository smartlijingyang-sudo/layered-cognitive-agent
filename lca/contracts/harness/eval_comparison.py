"""Deterministic comparison of baseline and current evaluation outcomes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvalComparison:
    expected_status: str
    actual_status: str
    missing_artifacts: tuple[str, ...] = ()
    unexpected_artifacts: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return self.expected_status == self.actual_status and not self.missing_artifacts

    def summary(self) -> str:
        return "passed" if self.passed else "regression detected"


__all__ = ["EvalComparison"]
