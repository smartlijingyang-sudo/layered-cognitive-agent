"""Small decorator API for executable declarative workflows."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from lca.contracts.harness.workflow import WorkflowMeta, WorkflowPhase, WorkflowPhaseContext
from lca.harness.workflow.engine import WorkflowEngine

PhaseFunction = Callable[[WorkflowPhaseContext], Awaitable[Any]]


@dataclass
class WorkflowScript:
    name: str
    _phases: dict[str, tuple[WorkflowPhase, PhaseFunction]] = field(default_factory=dict)

    def phase(
        self, name: str, *, deps: tuple[str, ...] = ()
    ) -> Callable[[PhaseFunction], PhaseFunction]:
        def register(fn: PhaseFunction) -> PhaseFunction:
            if name in self._phases:
                raise ValueError(f"phase already registered: {name}")
            self._phases[name] = (WorkflowPhase(name=name, deps=deps), fn)
            return fn

        return register

    @property
    def meta(self) -> WorkflowMeta:
        return WorkflowMeta(
            name=self.name, phases=tuple(phase for phase, _ in self._phases.values())
        )

    async def run(self) -> dict[str, Any]:
        return await WorkflowEngine().run(
            self.meta, lambda context: self._phases[context.phase.name][1](context)
        )


def agent(name: str) -> WorkflowScript:
    """Create a workflow script rooted at an agent-facing workflow name."""
    return WorkflowScript(name)


def phase(
    workflow: WorkflowScript, name: str, *, deps: tuple[str, ...] = ()
) -> Callable[[PhaseFunction], PhaseFunction]:
    """Register a script phase without reaching into the workflow object."""
    return workflow.phase(name, deps=deps)
