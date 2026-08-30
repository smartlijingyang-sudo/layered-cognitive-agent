"""Replayable evaluation case contract for Hermes regression suites."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    objective: str
    expected_status: str
    expected_artifacts: tuple[str, ...] = ()
    plan_version: str = "1"

    def __post_init__(self) -> None:
        if not self.case_id.strip() or not self.objective.strip():
            raise ValueError("evaluation case identity and objective must not be empty")
        if not self.expected_status.strip() or not self.plan_version.strip():
            raise ValueError("evaluation case status and plan version must not be empty")

    def matches(self, *, status: str, artifacts: tuple[str, ...]) -> bool:
        return status == self.expected_status and all(
            item in artifacts for item in self.expected_artifacts
        )


__all__ = ["EvalCase"]
