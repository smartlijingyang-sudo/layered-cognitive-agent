"""reflect sub-graph wiring + adapter + node tests.

Covers:
  - reflect.yaml loads + compiles without validation errors
  - LcaReflectCriticProvider default returns a Reflection artifact
  - LcaReflectCriticProvider with fixture_critic_name returns custom verdict
  - LcaReflectMemoryProvider with fixture_memory_name records calls
  - The full sub-graph runs via agent_lab's runner
"""

from __future__ import annotations

import sys
from pathlib import Path

from agent_lab.graph.compile import compile as compile_spec
from agent_lab.graphs import load_registry
from agent_lab.primitives.artifact import Artifact, ArtifactKind

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# (1) graph load + compile
# ---------------------------------------------------------------------------


def test_reflect_subgraph_loads_and_compiles() -> None:
    specs = load_registry("reflect")
    assert "reflect" in specs
    spec = specs["reflect"]
    assert {n.id for n in spec.nodes} == {"gather", "critic", "memory_extract", "memory_write"}
    bundle = compile_spec(spec, sub_registry=specs)
    assert bundle.spec_id == "reflect"
    flat = [nid for layer in bundle.layers for nid in layer]
    assert flat.index("gather") < flat.index("critic")
    assert flat.index("critic") < flat.index("memory_extract")
    assert flat.index("memory_extract") < flat.index("memory_write")


# ---------------------------------------------------------------------------
# (2) critic provider
# ---------------------------------------------------------------------------


def test_lca_reflect_critic_provider_default() -> None:
    """Default critic returns a Reflection artifact with ON_TRACK verdict."""
    from agent_lab.adapters.lca_reflect import LcaReflectCriticProvider

    provider = LcaReflectCriticProvider.from_node_config({})
    combined = Artifact(
        kind=ArtifactKind.FACT,
        content={
            "in_observation": {
                "observation_id": "obs_test",
                "success": True,
                "payload": "done",
            },
            "in_decision": {
                "decision_id": "dec_test",
                "action_type": "respond",
            },
        },
    )
    out = provider.critique(combined_artifact=combined)
    assert "reflection" in out
    reflection = out["reflection"]
    assert reflection.kind == ArtifactKind.FACT
    assert reflection.schema_ref == "reflection.v1"
    assert reflection.content["verdict"] == "on_track"
    assert reflection.content["reflection_id"]


def test_lca_reflect_critic_provider_with_fixture() -> None:
    """fixture_critic_name overrides the default with a custom verdict."""
    from agent_lab.adapters.lca_reflect import (
        LcaReflectCriticProvider,
        register_fixture_critic,
        unregister_fixture_critic,
    )

    name = "test-reflect-critic-fixture"

    class _CustomCritic:
        async def critique(self, state, observation):  # type: ignore[no-untyped-def]
            from lca.contracts.atoms.enums.enums import ReflectionVerdict
            from lca.contracts.models.core.execution.decision import Reflection

            return Reflection(
                reflection_id="refl_custom",
                verdict=ReflectionVerdict.NEEDS_CORRECTION,
                lesson="custom lesson from fixture",
            )

    register_fixture_critic(name, _CustomCritic())
    try:
        provider = LcaReflectCriticProvider.from_node_config(
            {"provider_config": {"fixture_critic_name": name}}
        )
        combined = Artifact(
            kind=ArtifactKind.FACT,
            content={
                "in_observation": {"observation_id": "obs_x", "success": False, "payload": None},
                "in_decision": {"decision_id": "dec_x", "action_type": "call_tool"},
            },
        )
        out = provider.critique(combined_artifact=combined)
        assert out["reflection"].content["reflection_id"] == "refl_custom"
        assert out["reflection"].content["verdict"] == "needs_correction"
        assert out["reflection"].content["lesson"] == "custom lesson from fixture"
    finally:
        unregister_fixture_critic(name)


# ---------------------------------------------------------------------------
# (3) memory provider
# ---------------------------------------------------------------------------


def test_lca_reflect_memory_provider_with_fixture() -> None:
    """fixture_memory_name records the update call."""
    from agent_lab.adapters.lca_reflect import (
        LcaReflectMemoryProvider,
        register_fixture_memory,
        unregister_fixture_memory,
    )

    name = "test-reflect-memory-fixture"

    class _RecordingMemory:
        def __init__(self) -> None:
            self.updates: list[dict] = []

        async def perceive(self, state):  # type: ignore[no-untyped-def]
            return state

        async def update(self, state, observation, reflection):  # type: ignore[no-untyped-def]
            self.updates.append(
                {
                    "state": state,
                    "observation": observation,
                    "reflection": reflection,
                }
            )

        def query(self, layer):  # type: ignore[no-untyped-def]
            return []

    mem = _RecordingMemory()
    register_fixture_memory(name, mem)
    try:
        provider = LcaReflectMemoryProvider.from_node_config(
            {"provider_config": {"fixture_memory_name": name}}
        )
        reflection_artifact = Artifact(
            kind=ArtifactKind.FACT,
            content={
                "reflection_id": "refl_test",
                "verdict": "on_track",
                "lesson": "test lesson",
            },
            schema_ref="reflection.v1",
        )
        memory_artifact = Artifact(
            kind=ArtifactKind.FACT,
            content={"items": [{"kind": "lesson", "text": "test lesson"}]},
            schema_ref="memory.candidates.v1",
        )
        out = provider.write(
            reflection_artifact=reflection_artifact,
            memory_artifact=memory_artifact,
        )
        assert len(mem.updates) == 1
        assert mem.updates[0]["reflection"].reflection_id == "refl_test"
        assert mem.updates[0]["reflection"].lesson == "test lesson"
        assert "reflection_out" in out
        assert "memory_extract_out" in out
        assert "reflect_signal" in out
        assert out["reflect_signal"].content["reflection_id"] == "refl_test"
        assert out["reflect_signal"].schema_ref == "reflect.signal.v1"
    finally:
        unregister_fixture_memory(name)


# ---------------------------------------------------------------------------
# (4) runner integration
# ---------------------------------------------------------------------------


def test_reflect_subgraph_runs_via_runner() -> None:
    """The reflect sub-graph runs end-to-end through agent_lab's runner."""
    from agent_lab.runtime.runner import run as run_graph

    specs = load_registry("reflect")
    reflect_spec = specs["reflect"]

    initial = {
        "in_observation": Artifact(
            kind=ArtifactKind.FACT,
            content={
                "observation_id": "obs_run",
                "success": True,
                "payload": "all good",
            },
            schema_ref="observation.v1",
        ),
        "in_decision": Artifact(
            kind=ArtifactKind.FACT,
            content={
                "decision_id": "dec_run",
                "action_type": "respond",
                "rationale": "test",
                "confidence": 1.0,
                "tool_calls": [],
            },
            schema_ref="decision.v1",
        ),
        "in_prior_reflection": Artifact(
            kind=ArtifactKind.FACT,
            content={},
            schema_ref="reflection.v1",
        ),
    }
    trace = run_graph(reflect_spec, initial=initial, sub_registry=specs)
    assert "reflection_out" in trace.final_artifacts, (
        f"reflect sub-graph must emit reflection_out; got {sorted(trace.final_artifacts)}"
    )
    reflection = trace.final_artifacts["reflection_out"]
    assert reflection.kind == ArtifactKind.FACT
    assert reflection.content["verdict"] == "on_track"
    assert "memory_extract_out" in trace.final_artifacts
    assert "reflect_signal" in trace.final_artifacts
    signal = trace.final_artifacts["reflect_signal"]
    assert signal.schema_ref == "reflect.signal.v1"
