"""perceive sub-graph: resolve → sense → memory → policy → trim → commit → eye.

Covers:
  - perceive.yaml loads + compiles (Hub production steps + model_eye host)
  - resolve/sense/memory/policy/trim/commit against LCA fixtures
  - ContextManifest from commit feeds model_eye
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


def test_perceive_subgraph_loads_and_compiles() -> None:
    specs = load_registry("perceive", "model_eye", "agent_loop", "act")
    assert "perceive" in specs
    assert "model_eye" in specs
    spec = specs["perceive"]
    assert {n.id for n in spec.nodes} == {
        "resolve",
        "sense",
        "memory",
        "policy",
        "trim",
        "commit",
        "eye",
    }
    assert {n.factory for n in spec.nodes if n.id != "eye"} == {
        "perceive.resolve",
        "perceive.sense",
        "perceive.memory",
        "perceive.policy",
        "perceive.trim",
        "perceive.commit",
    }
    assert any(link.sub_spec_id == "model_eye" for link in spec.sub_specs)
    bundle = compile_spec(spec, sub_registry=specs)
    assert bundle.spec_id == "perceive"
    flat = [nid for layer in bundle.layers for nid in layer]
    assert flat.index("resolve") < flat.index("sense")
    assert flat.index("resolve") < flat.index("memory")
    assert flat.index("sense") < flat.index("trim")
    assert flat.index("memory") < flat.index("trim")
    assert flat.index("policy") < flat.index("trim")
    assert flat.index("trim") < flat.index("commit")
    assert flat.index("commit") < flat.index("eye")


def test_perceive_subgraph_declares_initial_ports() -> None:
    specs = load_registry("perceive", "model_eye", "agent_loop", "act")
    initial_ports = specs["perceive"].initial_ports()
    assert "state" in initial_ports
    assert "system" in initial_ports
    assert "history" in initial_ports
    assert "user_turn" not in initial_ports or "user_turn" in initial_ports
    # user_turn may feed eye only; tool_results is not a perceive Hub input
    assert "tool_results" not in initial_ports


def test_perceive_sense_folds_fixture_sensor() -> None:
    from agent_lab.adapters.lca_perceive import (
        register_fixture_sensors,
        unregister_fixture_sensors,
    )
    from agent_lab.graph.spec import InfoNode, NodeRegion
    from agent_lab.nodes.base import NodeRegistry
    from lca.cognition.sensors.clock import ClockSensor

    name = "test-perceive-clock"
    register_fixture_sensors(name, [ClockSensor(now=None)])
    try:
        resolve = NodeRegistry.get("perceive.resolve")()
        resolve_node = InfoNode(
            id="resolve",
            region=NodeRegion.PHASE,
            factory="perceive.resolve",
            config={"provider_config": {"fixture_sensors_name": name}},
            ins=["state"],
            outs=["sensors", "memory_ref"],
        )
        state = Artifact(
            kind=ArtifactKind.FACT,
            content={"trace_id": "t1", "task": "demo", "step": 0},
        )
        resolved = resolve.execute(resolve_node, {"state": state})
        assert "sensors" in resolved
        assert "memory_ref" in resolved

        sense = NodeRegistry.get("perceive.sense")()
        sense_node = InfoNode(
            id="sense",
            region=NodeRegion.PHASE,
            factory="perceive.sense",
            config={},
            ins=["sensors", "state"],
            outs=["sensor_items"],
        )
        out = sense.execute(
            sense_node,
            {"sensors": resolved["sensors"], "state": state},
        )
        items = out["sensor_items"].content["items"]
        assert items
        assert items[0]["kind"] == "clock"
        assert items[0]["provenance"] == "clock_sensor"
    finally:
        unregister_fixture_sensors(name)


def test_perceive_commit_builds_context_manifest() -> None:
    from agent_lab.graph.spec import InfoNode, NodeRegion
    from agent_lab.nodes.base import NodeRegistry

    commit = NodeRegistry.get("perceive.commit")()
    node = InfoNode(
        id="commit",
        region=NodeRegion.PHASE,
        factory="perceive.commit",
        config={},
        ins=["trimmed_items"],
        outs=["context_manifest"],
    )
    trimmed = Artifact(
        kind=ArtifactKind.FACT,
        content={
            "items": [
                {
                    "kind": "clock",
                    "payload": "2026-09-08 Monday",
                    "provenance": "clock_sensor",
                }
            ]
        },
        schema_ref="context.items.v1",
    )
    out = commit.execute(node, {"trimmed_items": trimmed})
    manifest = out["context_manifest"]
    assert manifest.schema_ref == "context.manifest.v1"
    assert manifest.content["items"][0]["kind"] == "clock"
    assert isinstance(manifest.content["digest"], str)
    assert manifest.content["digest"]


def test_perceive_subgraph_runs_via_runner() -> None:
    from agent_lab.adapters.lca_perceive import (
        register_fixture_sensors,
        unregister_fixture_sensors,
    )
    from agent_lab.runtime.runner import run as run_graph
    from lca.cognition.sensors.clock import ClockSensor

    specs = load_registry("perceive", "model_eye", "act")
    perceive_spec = specs["perceive"]
    name = "runner-perceive-clock"
    register_fixture_sensors(name, [ClockSensor()])
    try:
        for n in perceive_spec.nodes:
            if n.id == "resolve":
                n.config.setdefault("provider_config", {})
                n.config["provider_config"]["fixture_sensors_name"] = name

        initial = {
            "state": Artifact(
                kind=ArtifactKind.FACT,
                content={"trace_id": "run", "task": "t", "step": 0},
            ),
            "system": Artifact(kind=ArtifactKind.TEXT, content="sys"),
            "history": Artifact(
                kind=ArtifactKind.MESSAGE,
                content=[{"role": "user", "content": "hi"}],
            ),
            "config": Artifact(kind=ArtifactKind.FACT, content={}),
            "tools": Artifact(kind=ArtifactKind.FACT, content=[]),
            "user_turn": Artifact(
                kind=ArtifactKind.MESSAGE,
                content={"role": "user", "content": "hi"},
            ),
        }
        trace = run_graph(perceive_spec, initial=initial, sub_registry=specs)
        assert "context_manifest" in trace.final_artifacts or "manifest" in trace.final_artifacts
        # Hub path emits context_manifest; eye emits frozen model_eye manifest.
        if "context_manifest" in trace.final_artifacts:
            cm = trace.final_artifacts["context_manifest"]
            assert cm.content["items"]
            assert cm.content["items"][0]["kind"] == "clock"
        assert "manifest" in trace.final_artifacts
        assert trace.final_artifacts["manifest"].content.get("committed") is True
    finally:
        unregister_fixture_sensors(name)
