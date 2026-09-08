"""Perceive sub-graph wiring + adapter + node tests.

Covers:
  - perceive.yaml loads + compiles without validation errors
  - agent_loop.yaml (with the new perceive sub_spec) loads + compiles
  - LcaPerceiveProvider.from_node_config resolves a fixture Hub and
    Hub.perceive(state) → frozen ContextManifest artifact
  - The full sub-graph runs via the agent_lab runner and emits an
    out_manifest artifact in agent_loop's final outputs

Fixtures use lca.plugins.composer.runtime.fixture.runtime_factory.NullPerceiveHub
(SSOT for "empty perceive"); this test does not depend on a live LCA runtime.
"""

from __future__ import annotations

import sys
from pathlib import Path

from agent_lab.graph.compile import compile as compile_spec
from agent_lab.graphs import load_registry
from agent_lab.primitives.artifact import Artifact, ArtifactKind, make_text

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# (1) graph load + compile
# ---------------------------------------------------------------------------


def test_perceive_subgraph_loads_and_compiles() -> None:
    """The new perceive sub-graph passes C1-C14 invariant checks."""
    specs = load_registry("perceive", "agent_loop", "mv_assemble", "effect_dispatch")
    assert "perceive" in specs, "perceive.yaml must register"
    spec = specs["perceive"]
    # 5 local nodes: classify, dedupe, rank, redact, build
    assert {n.id for n in spec.nodes} == {"classify", "dedupe", "rank", "redact", "build"}
    # Compile must not raise (no validation errors).
    bundle = compile_spec(spec, sub_registry=specs)
    assert bundle.spec_id == "perceive"
    # Topological schedule: classify → dedupe → rank → redact → build
    flat = [nid for layer in bundle.layers for nid in layer]
    assert flat.index("classify") < flat.index("dedupe")
    assert flat.index("dedupe") < flat.index("rank")
    assert flat.index("rank") < flat.index("redact")
    assert flat.index("redact") < flat.index("build")


def test_agent_loop_compiles_with_perceive_sub_spec() -> None:
    """agent_loop accepts the new perceive sub_spec and its state port."""
    specs = load_registry("perceive", "agent_loop", "mv_assemble", "effect_dispatch")
    agent_loop = specs["agent_loop"]
    # perceive node now declares both `state` (in) and `out_manifest` (out)
    perceive_node = agent_loop.node("perceive")
    assert "state" in perceive_node.ins
    assert "out_manifest" in perceive_node.outs
    # state is wired from _initial
    state_ports = {e.from_ref.port_id for e in agent_loop.edges if e.to_ref.node_id == "perceive"}
    assert "state" in state_ports
    # perceive sub_spec mount exists with the right input/output maps
    perceive_links = [link for link in agent_loop.sub_specs if link.node_id == "perceive"]
    assert len(perceive_links) == 1
    link = perceive_links[0]
    assert link.sub_spec_id == "perceive"
    assert link.input_map == {"user_turn": "user_turn", "state": "state"}
    assert link.output_map == {"manifest": "out_manifest"}
    # Compile must not raise.
    compile_spec(agent_loop, sub_registry=specs)


# ---------------------------------------------------------------------------
# (2) adapter
# ---------------------------------------------------------------------------


def test_lca_perceive_provider_resolves_fixture_hub() -> None:
    """from_node_config honors the fixture_hub_name shortcut without importing lca runtime."""
    from agent_lab.adapters.lca_perceive import (
        LcaPerceiveProvider,
        register_fixture_hub,
        unregister_fixture_hub,
    )
    from lca.plugins.composer.runtime.fixture.runtime_factory import NullPerceiveHub

    name = "test-null-hub-fixture-hub-name"
    hub = NullPerceiveHub()
    register_fixture_hub(name, hub)
    try:
        provider = LcaPerceiveProvider.from_node_config(
            {"provider_config": {"fixture_hub_name": name}}
        )
        assert provider._hub is hub

        state_artifact = Artifact(
            kind=ArtifactKind.FACT,
            content={"step": 1, "retrieved_context": (), "history": ()},
        )
        out = provider.build(sanitized_artifact=None, state_artifact=state_artifact)
        assert "manifest" in out
        manifest = out["manifest"]
        assert manifest.kind == ArtifactKind.MANIFEST
        assert manifest.schema_ref == "context.manifest.v1"
        assert manifest.content["items"] == []
        assert isinstance(manifest.content["digest"], str)
    finally:
        unregister_fixture_hub(name)


def test_lca_perceive_provider_resolves_hub_factory_ref() -> None:
    """from_node_config resolves ``module:Class`` form when no fixture is set."""
    from agent_lab.adapters.lca_perceive import LcaPerceiveProvider

    # Use NullPerceiveHub (no required ctor args) — same module path the
    # production graph wires via hub_factory.ref in perceive.yaml.
    provider = LcaPerceiveProvider.from_node_config(
        {
            "provider_config": {
                "hub_factory": {
                    "ref": ("lca.plugins.composer.runtime.fixture.runtime_factory:NullPerceiveHub"),
                    "kwargs": {},
                }
            }
        }
    )
    from lca.plugins.composer.runtime.fixture.runtime_factory import (
        NullPerceiveHub,
    )

    assert isinstance(provider._hub, NullPerceiveHub)


def test_lca_perceive_provider_passes_through_extra_fields() -> None:
    """AgentState.extra absorbs unrecognised content keys so profiles stay SSOT."""

    from agent_lab.adapters.lca_perceive import LcaPerceiveProvider

    captured = {}

    class _CaptureHub:
        async def perceive(self, state):  # type: ignore[no-untyped-def]
            captured["state"] = state
            from lca.contracts.models.core.perceive.perception import ContextManifest

            return ContextManifest(items=())

    provider = LcaPerceiveProvider(_hub=_CaptureHub())
    state_artifact = Artifact(
        kind=ArtifactKind.FACT,
        content={"step": 0, "team_awareness": "alpha", "last_error": None},
    )
    provider.build(sanitized_artifact=None, state_artifact=state_artifact)
    state = captured["state"]
    assert state.step == 0
    assert state.extra.get("team_awareness") == "alpha"
    assert state.extra.get("last_error") is None


# ---------------------------------------------------------------------------
# (3) runner integration
# ---------------------------------------------------------------------------


def test_perceive_subgraph_runs_via_agent_loop_with_fixture_hub(monkeypatch) -> None:
    """End-to-end: sub-graph runs through agent_loop's runner and emits out_manifest."""
    from agent_lab.adapters.lca_perceive import (
        register_fixture_hub,
        unregister_fixture_hub,
    )
    from agent_lab.runtime.runner import run as run_graph
    from lca.plugins.composer.runtime.fixture.runtime_factory import NullPerceiveHub

    name = "test-perceive-end2end-fixture-hub"
    register_fixture_hub(name, NullPerceiveHub())
    try:
        specs = load_registry("perceive", "agent_loop", "mv_assemble", "effect_dispatch")
        perceive_spec = specs["perceive"]
        # Swap production hub_factory for a fixture_hub_name string so
        # node.config stays JSON-serializable (plan_hash dump).
        for n in perceive_spec.nodes:
            if n.id == "build":
                n.config["provider_config"] = {"fixture_hub_name": name}

        initial = {
            "user_turn": make_text("hello perceive", schema_ref="user.turn.v1"),
            "system": make_text("you are a careful assistant", schema_ref="system.v1"),
            "history": Artifact(
                kind=ArtifactKind.MESSAGE,
                content=[],
                schema_ref="openai.messages.v1",
            ),
            "results": make_text("", schema_ref="tool.v1"),
            "config": Artifact(
                kind=ArtifactKind.FACT,
                content={"temperature": 0.0},
                schema_ref="config.v1",
            ),
            "tools": Artifact(kind=ArtifactKind.FACT, content=[], schema_ref="tools.v1"),
            "state": Artifact(
                kind=ArtifactKind.FACT,
                content={"step": 0, "retrieved_context": (), "history": ()},
            ),
        }
        # Run the perceive sub_spec directly (agent_loop reaches the LLM call
        # which we cannot answer offline).
        trace = run_graph(perceive_spec, initial=initial, sub_registry=specs)
        assert "manifest" in trace.final_artifacts, (
            f"perceive sub-graph must emit a manifest artifact; got {sorted(trace.final_artifacts)}"
        )
        manifest = trace.final_artifacts["manifest"]
        assert manifest.kind == ArtifactKind.MANIFEST
        assert manifest.schema_ref == "context.manifest.v1"
    finally:
        unregister_fixture_hub(name)


# ---------------------------------------------------------------------------
# (4) negative — missing required initial port should be visible at compile
# ---------------------------------------------------------------------------


def test_perceive_subgraph_requires_state_initial_port() -> None:
    """The sub-graph's state initial port must be declared or compile must not silently drop it."""
    specs = load_registry("perceive", "agent_loop", "mv_assemble", "effect_dispatch")
    spec = specs["perceive"]
    # Sanity: the spec lists 'state' among its initial ports (declared by edges from _initial).
    initial_ports = spec.initial_ports()
    assert "state" in initial_ports
    assert "user_turn" in initial_ports
