"""reflect sub-graph: join → critique → extract.

Covers:
  - reflect.yaml loads + compiles as a three-node chain
  - LcaReflectCriticProvider default / fixture verdicts
  - extract derives memory candidates from lesson (no MemorySystem.write)
  - full sub-graph runs via agent_lab's runner
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
    assert {n.id for n in spec.nodes} == {"join", "critique", "extract"}
    assert {n.factory for n in spec.nodes} == {
        "reflect.join",
        "reflect.critique",
        "reflect.extract",
    }
    bundle = compile_spec(spec, sub_registry=specs)
    assert bundle.spec_id == "reflect"
    flat = [nid for layer in bundle.layers for nid in layer]
    assert flat.index("join") < flat.index("critique")
    assert flat.index("critique") < flat.index("extract")


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
# (3) extract: pure candidates — no MemorySystem.write
# ---------------------------------------------------------------------------


def test_reflect_extract_derives_candidates_from_lesson() -> None:
    """reflect.extract turns lesson/correction into candidates; no durable write."""
    from agent_lab.nodes.reflect.extract.plugin import ReflectExtract

    node = ReflectExtract.__new__(ReflectExtract)
    node.config = {}
    node.outs = ["reflection_out", "memory_candidates", "reflect_signal"]
    reflection = Artifact(
        kind=ArtifactKind.FACT,
        content={
            "reflection_id": "refl_lesson",
            "verdict": "needs_correction",
            "lesson": "retry with smaller scope",
            "correction": {"decision_id": "dec_fix", "action_type": "call_tool"},
            "extra": {},
        },
        schema_ref="reflection.v1",
    )
    out = node.execute(node, {"reflection": reflection})
    assert out["reflection_out"].content["reflection_id"] == "refl_lesson"
    items = out["memory_candidates"].content["items"]
    kinds = {item["kind"] for item in items}
    assert kinds == {"lesson", "correction"}
    assert out["memory_candidates"].schema_ref == "memory.candidates.v1"
    assert out["reflect_signal"].content["reflection_id"] == "refl_lesson"
    assert out["reflect_signal"].content["verdict"] == "needs_correction"
    assert out["reflect_signal"].schema_ref == "reflect.signal.v1"


def test_reflect_extract_empty_reflection_yields_no_candidates() -> None:
    from agent_lab.nodes.reflect.extract.plugin import ReflectExtract

    node = ReflectExtract.__new__(ReflectExtract)
    node.config = {}
    node.outs = ["reflection_out", "memory_candidates", "reflect_signal"]
    reflection = Artifact(
        kind=ArtifactKind.FACT,
        content={"reflection_id": "refl_empty", "verdict": "on_track", "lesson": None},
        schema_ref="reflection.v1",
    )
    out = node.execute(node, {"reflection": reflection})
    assert out["memory_candidates"].content["items"] == []
    assert out["reflect_signal"].content["verdict"] == "on_track"


# ---------------------------------------------------------------------------
# (4) runner integration
# ---------------------------------------------------------------------------


def test_reflect_subgraph_runs_via_runner() -> None:
    """The reflect sub-graph runs end-to-end through agent_lab's runner."""
    from agent_lab.adapters.lca_reflect import (
        register_fixture_critic,
        unregister_fixture_critic,
    )
    from agent_lab.runtime.runner import run as run_graph

    name = "test-reflect-runner-critic"

    class _LessonCritic:
        async def critique(self, state, observation):  # type: ignore[no-untyped-def]
            from lca.contracts.atoms.enums.enums import ReflectionVerdict
            from lca.contracts.models.core.execution.decision import Reflection

            return Reflection(
                reflection_id="refl_run",
                verdict=ReflectionVerdict.NEEDS_CORRECTION,
                lesson="prefer smaller tool args",
            )

    register_fixture_critic(name, _LessonCritic())
    try:
        specs = load_registry("reflect")
        # Patch the critique node config so the runner uses the fixture critic.
        reflect_spec = specs["reflect"]
        for n in reflect_spec.nodes:
            if n.id == "critique":
                n.config = {
                    **dict(n.config or {}),
                    "provider_kind": "lca",
                    "provider_ref": "agent_lab.adapters.lca_reflect:LcaReflectCriticProvider",
                    "provider_config": {"fixture_critic_name": name},
                }

        initial = {
            "in_observation": Artifact(
                kind=ArtifactKind.FACT,
                content={
                    "observation_id": "obs_run",
                    "success": False,
                    "payload": "tool failed",
                },
                schema_ref="observation.v1",
            ),
            "in_decision": Artifact(
                kind=ArtifactKind.FACT,
                content={
                    "decision_id": "dec_run",
                    "action_type": "call_tool",
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
            f"reflect must emit reflection_out; got {sorted(trace.final_artifacts)}"
        )
        reflection = trace.final_artifacts["reflection_out"]
        assert reflection.content["verdict"] == "needs_correction"
        assert reflection.content["lesson"] == "prefer smaller tool args"
        assert "memory_candidates" in trace.final_artifacts
        items = trace.final_artifacts["memory_candidates"].content["items"]
        assert any(i.get("kind") == "lesson" for i in items)
        assert "reflect_signal" in trace.final_artifacts
        signal = trace.final_artifacts["reflect_signal"]
        assert signal.schema_ref == "reflect.signal.v1"
        assert signal.content["reflection_id"] == "refl_run"
    finally:
        unregister_fixture_critic(name)
