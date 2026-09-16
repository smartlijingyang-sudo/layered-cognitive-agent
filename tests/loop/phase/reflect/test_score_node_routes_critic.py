"""Regression: ``phase.reflect.score`` must route through ``brain.reflect``.

Bug: prior to this fix, the executor preferred the ``cognitive_reflection_pipeline``
capability and called ``pipeline.reflect(..., critic=None)``. With no critic
bound, :class:`StandardCognitiveReflectionPipeline` short-circuits to
``Reflection(verdict=ON_TRACK, lesson=None)`` every step — the outer loop
never learned a tool had succeeded, and the agent re-issued the same tool
call until budget exhaustion.

Fix: prefer ``brain.reflect(state, observation)`` when the runtime exposes
one. ``ModularBrain.reflect`` already wires the profile-selected critic into
the pipeline; this path reaches ``SimpleCritic.critique`` and emits
``critic.eval.start/end`` spine facts with non-empty ``state_id``.

This test pins the dispatch shape — both that ``brain`` wins is selected
and that the resulting ``Reflection`` carries a non-ON_TRACK verdict when
the brain's critic chooses one.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock

from lca.contracts.atoms.enums.enums import ReflectionVerdict
from lca.contracts.models.core.execution.decision import Observation, Reflection
from lca.contracts.models.core.state.state import AgentState
from lca.nodes.reflect.score.score import ReflectScoreExecutor


@dataclass
class _FakeRuntime:
    """Minimal context.runtime mapping; the executor reads three keys."""

    def __init__(
        self,
        *,
        brain: Any = None,
        pipeline: Any = None,
        agent_state: AgentState | None = None,
    ) -> None:
        self._values: dict[str, Any] = {}
        if brain is not None:
            self._values["brain"] = brain
        if pipeline is not None:
            self._values["cognitive_reflection_pipeline"] = pipeline
        if agent_state is not None:
            self._values["agent_state"] = agent_state

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)


@dataclass
class _StubBrain:
    """Brain stand-in whose ``reflect`` we can introspect.

    Implements ``think`` so ``runtime_checkable`` ``Brain`` Protocol matches.
    """

    reflect: AsyncMock  # type: ignore[type-arg]
    think: AsyncMock = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.think is None:
            self.think = AsyncMock()


@dataclass
class _StubPipeline:
    """Pipeline stand-in whose ``reflect`` we can introspect."""

    reflect: AsyncMock  # type: ignore[type-arg]


def _observation() -> Observation:
    return Observation(
        observation_id="obs-1",
        success=True,
        payload={"output": "ls result"},
    )


def _agent_state() -> AgentState:
    return AgentState(trace_id="trace-1", task="t", budget=None)  # type: ignore[arg-type]


def test_score_node_prefers_brain_over_pipeline_when_brain_present() -> None:
    """When the runtime exposes both brain and pipeline, brain wins."""
    brain_reflection = Reflection(
        reflection_id="refl-brain",
        verdict=ReflectionVerdict.DEGRADED_BUT_COMPLETED,
        lesson="tool ls returned expected output",
    )
    brain = _StubBrain(reflect=AsyncMock(return_value=brain_reflection))
    pipeline_reflection = Reflection(
        reflection_id="refl-pipeline",
        verdict=ReflectionVerdict.ON_TRACK,
        lesson=None,
    )
    pipeline = _StubPipeline(reflect=AsyncMock(return_value=pipeline_reflection))

    runtime = _FakeRuntime(brain=brain, pipeline=pipeline, agent_state=_agent_state())
    executor = ReflectScoreExecutor()

    output = asyncio.run(
        executor.node_execute(
            context=type("_C", (), {"runtime": runtime})(),
            input=type(
                "_I",
                (),
                {
                    "port_values": {
                        "observation": _observation(),
                        "state": _agent_state(),
                        "cognitive_reflection_pipeline": pipeline,
                    }
                },
            )(),
        )
    )

    # brain reflects must have been invoked exactly once.
    assert brain.reflect.await_count == 1, (
        f"expected brain.reflect to be called once when brain is wired, got "
        f"{brain.reflect.await_count}"
    )
    # pipeline reflects must NOT have been called — the previous code routed
    # here with critic=None and short-circuited.
    assert pipeline.reflect.await_count == 0, (
        f"pipeline.reflect must be bypassed when brain is wired; got "
        f"{pipeline.reflect.await_count} calls"
    )
    # The returned reflection is the brain's (with verdict, lesson).
    payload = output.port_values["reflection"]
    assert payload is brain_reflection
    assert payload.verdict is ReflectionVerdict.DEGRADED_BUT_COMPLETED
    assert payload.lesson == "tool ls returned expected output"


def test_score_node_falls_back_to_pipeline_when_brain_missing() -> None:
    """Backward-compat: profiles without a brain still use the pipeline path."""
    pipeline_reflection = Reflection(
        reflection_id="refl-pipeline",
        verdict=ReflectionVerdict.ON_TRACK,
        lesson=None,
    )
    pipeline = _StubPipeline(reflect=AsyncMock(return_value=pipeline_reflection))

    runtime = _FakeRuntime(brain=None, pipeline=pipeline, agent_state=_agent_state())
    executor = ReflectScoreExecutor()

    output = asyncio.run(
        executor.node_execute(
            context=type("_C", (), {"runtime": runtime})(),
            input=type(
                "_I",
                (),
                {
                    "port_values": {
                        "observation": _observation(),
                        "state": _agent_state(),
                        "cognitive_reflection_pipeline": pipeline,
                    }
                },
            )(),
        )
    )

    assert pipeline.reflect.await_count == 1
    assert output.port_values["reflection"] is pipeline_reflection


def test_score_node_returns_none_payload_when_brain_and_pipeline_missing() -> None:
    """No brain, no pipeline → None payload (caller degrades gracefully)."""
    runtime = _FakeRuntime(brain=None, pipeline=None, agent_state=_agent_state())
    executor = ReflectScoreExecutor()

    output = asyncio.run(
        executor.node_execute(
            context=type("_C", (), {"runtime": runtime})(),
            input=type(
                "_I",
                (),
                {
                    "port_values": {
                        "observation": _observation(),
                        "state": _agent_state(),
                    }
                },
            )(),
        )
    )

    assert output.port_values["reflection"] is None
