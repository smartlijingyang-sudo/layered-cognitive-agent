"""Perceive sub-graph wiring tests.

Covers:
  - perceive.yaml loads + compiles (with nested model_eye)
  - expected node set including the eye host
  - perceive.aggregate composes sensors into perceive.bundle
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
    """perceive.yaml passes invariant checks and exposes the v3 node set + eye."""
    specs = load_registry("perceive", "model_eye", "agent_loop", "act")
    assert "perceive" in specs
    assert "model_eye" in specs
    spec = specs["perceive"]
    assert {n.id for n in spec.nodes} == {
        "sense_user",
        "sense_tool_results",
        "memory_resolve",
        "memory_query",
        "memory_normalize",
        "perceive_aggregate",
        "eye",
    }
    assert any(link.sub_spec_id == "model_eye" for link in spec.sub_specs)
    bundle = compile_spec(spec, sub_registry=specs)
    assert bundle.spec_id == "perceive"


def test_perceive_subgraph_declares_initial_ports() -> None:
    """Sensing + header ports that feed model_eye via the eye host."""
    specs = load_registry("perceive", "model_eye", "agent_loop", "act")
    initial_ports = specs["perceive"].initial_ports()
    assert "user_turn" in initial_ports
    assert "tool_results" in initial_ports
    assert "system" in initial_ports
    assert "history" in initial_ports


def test_perceive_aggregate_combines_three_sensors_into_bundle() -> None:
    """perceive.aggregate → perceive.bundle (not ContextManifest)."""
    from agent_lab.nodes.perceive.aggregate.plugin import PerceiveAggregate

    node = PerceiveAggregate.__new__(PerceiveAggregate)
    node.config = {"to": "bundle"}
    node.outs = ["bundle"]

    inputs = {
        "user_turn": Artifact(
            kind=ArtifactKind.MESSAGE,
            content={"role": "user", "content": "hi"},
        ),
        "tool_results": Artifact(
            kind=ArtifactKind.MESSAGE,
            content=[{"role": "tool", "tool_call_id": "c1", "content": "out"}],
        ),
        "retrieved_context": Artifact(
            kind=ArtifactKind.FACT,
            content=[{"kind": "memory", "payload": {"x": 1}}],
        ),
    }
    out = node.execute(node, inputs)
    assert "bundle" in out
    bundle = out["bundle"]
    assert bundle.kind == ArtifactKind.FACT
    assert bundle.schema_ref == "perceive.bundle.v1"

    items = bundle.content["items"]
    assert len(items) == 3
    assert items[0]["provenance"] == "sense.user"
    assert items[1]["provenance"] == "sense.tool_results"
    assert items[2].get("kind") == "memory"
    assert isinstance(bundle.content["digest"], str)
    assert len(bundle.content["digest"]) == 64

    out2 = node.execute(node, inputs)
    assert out2["bundle"].content["digest"] == bundle.content["digest"]


def test_perceive_aggregate_handles_missing_sensors() -> None:
    """All three inputs optional; empty → empty items, valid bundle."""
    from agent_lab.nodes.perceive.aggregate.plugin import PerceiveAggregate

    node = PerceiveAggregate.__new__(PerceiveAggregate)
    node.config = {"to": "bundle"}
    node.outs = ["bundle"]
    out = node.execute(node, {})
    assert out["bundle"].content["items"] == []
    assert len(out["bundle"].content["digest"]) == 64


def test_model_eye_freeze_requires_user_role() -> None:
    """model_eye.freeze is the sole ContextManifest producer; fail-loud on missing roles."""
    from agent_lab.nodes.model_eye.freeze.plugin import ModelEyeFreeze

    node = ModelEyeFreeze.__new__(ModelEyeFreeze)
    node.config = {"required_roles": ["user"], "to": "manifest"}
    node.outs = ["manifest"]
    try:
        node.execute(
            node,
            {
                "messages": Artifact(
                    kind=ArtifactKind.MESSAGE,
                    content=[{"role": "system", "content": "x"}],
                )
            },
        )
        raise AssertionError("expected ValueError for missing user role")
    except ValueError as exc:
        assert "required roles missing" in str(exc)

    ok = node.execute(
        node,
        {
            "messages": Artifact(
                kind=ArtifactKind.MESSAGE,
                content=[{"role": "user", "content": "hi"}],
            )
        },
    )
    assert ok["manifest"].kind == ArtifactKind.MANIFEST
    assert ok["manifest"].content["committed"] is True
    assert ok["manifest"].schema_ref == "context.manifest.v1"
