"""Convergence task sensor tests (ADR-0196)."""

from __future__ import annotations

import asyncio

from lca.cognition.convergence.constants import TASK_CLASS_MANIFEST_KIND
from lca.cognition.convergence.task_class import resolve_task_class
from lca.cognition.sensors.convergence_task import ConvergenceTaskSensor
from lca.contracts.models.core.perceive.perception import ContextItem, ContextManifest
from lca.contracts.models.core.perceive.projection import PerceiveProjection
from lca.contracts.models.core.state.state import AgentState, Budget


def test_sensor_emits_task_class_hint() -> None:
    state = AgentState(
        trace_id="t",
        task="用python写一个图计划的笑话",
        budget=Budget(),
    )
    items = asyncio.run(ConvergenceTaskSensor().read(state))
    assert len(items) == 1
    assert items[0].kind == TASK_CLASS_MANIFEST_KIND
    assert items[0].payload == "informative_text"


def test_resolve_prefers_sensor_hint_over_regex() -> None:
    manifest = ContextManifest(
        digest="d",
        items=(
            ContextItem(
                kind=TASK_CLASS_MANIFEST_KIND,
                payload="visual_artifact",
                provenance="sensor.convergence-task",
            ),
        ),
    )
    state = AgentState(
        trace_id="t",
        task="用python写一个图计划的笑话",
        budget=Budget(),
        perceive=PerceiveProjection(manifest=manifest, digest="d", step=1),
    )
    assert resolve_task_class(state) == "visual_artifact"
