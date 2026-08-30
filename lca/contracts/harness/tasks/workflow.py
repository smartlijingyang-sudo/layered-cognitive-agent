"""Declarative workflow DAG contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class WorkflowPhase:
    """One named unit of work and the phases it depends upon."""

    name: str
    deps: tuple[str, ...] = ()
    isolation: Literal["task"] = "task"


@dataclass(frozen=True)
class WorkflowMeta:
    """A fully declarative, acyclic workflow definition."""

    name: str
    phases: tuple[WorkflowPhase, ...]


@dataclass(frozen=True)
class WorkflowPhaseContext:
    """Inputs visible to a phase after all its dependencies complete."""

    workflow: WorkflowMeta
    phase: WorkflowPhase
    dependency_results: dict[str, Any]


@dataclass(frozen=True)
class WorkflowProgress:
    """An immutable workflow progress snapshot emitted after each DAG wave."""

    completed: tuple[str, ...]
    pending: tuple[str, ...]

    @property
    def done(self) -> bool:
        return not self.pending
