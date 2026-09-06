"""Convergence control plane — delivery evidence and verdicts (ADR-0196)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ConvergenceKind = Literal[
    "continue",
    "nudge",
    "force_respond",
    "force_stop",
    "grace_respond",
]

TaskClass = Literal[
    "informative_text",
    "visual_artifact",
    "code_demo",
    "mixed",
    "unknown",
]


@dataclass(frozen=True, slots=True)
class DeliveryEvidence:
    """Folded view: operational success vs user-visible delivery (CV1)."""

    task_class: TaskClass
    artifact_count: int
    has_user_visible_text: bool
    producer_success_since_task: int
    satisfied: bool
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_class": self.task_class,
            "artifact_count": self.artifact_count,
            "has_user_visible_text": self.has_user_visible_text,
            "producer_success_since_task": self.producer_success_since_task,
            "satisfied": self.satisfied,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class ConvergenceVerdict:
    kind: ConvergenceKind
    rationale: str
    evidence: DeliveryEvidence
    extra: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "ConvergenceKind",
    "ConvergenceVerdict",
    "DeliveryEvidence",
    "TaskClass",
]
