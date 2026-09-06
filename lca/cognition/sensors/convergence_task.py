"""ConvergenceTaskSensor — perceive-owned TaskClass hint (ADR-0196)."""

from __future__ import annotations

from lca.cognition.convergence.constants import TASK_CLASS_MANIFEST_KIND
from lca.cognition.convergence.task_class import classify_task
from lca.contracts.models.core.perceive.perception import ContextItem
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols import Sensor


class ConvergenceTaskSensor(Sensor):
    """Publish deterministic TaskClass for prompt and convergence fold."""

    async def read(self, state: AgentState) -> list[ContextItem]:
        task_class = classify_task(state.task or "")
        return [
            ContextItem(
                kind=TASK_CLASS_MANIFEST_KIND,
                payload=task_class,
                provenance="sensor.convergence-task",
            )
        ]


def build_convergence_task_sensor() -> Sensor:
    return ConvergenceTaskSensor()


__all__ = ["ConvergenceTaskSensor", "build_convergence_task_sensor"]
