"""observe_wildcard sub-graph tests.

Covers:
  - observe_wildcard.yaml loads + compiles without validation errors.
  - LcaControlObserveWildcardProvider default returns verdict=allow.
  - LcaControlObserveWildcardProvider with fixture callable denies.
  - Full sub-graph runs via agent_lab's runner.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the new control node is registered.
import agent_lab.nodes.control.observe_wildcard_node.plugin  # noqa: F401
from agent_lab.graph.compile import compile as compile_spec
from agent_lab.graphs import load_registry
from agent_lab.primitives.artifact import Artifact, ArtifactKind

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# (1) graph load + compile
# ---------------------------------------------------------------------------


def test_observe_wildcard_subgraph_loads_and_compiles() -> None:
    specs = load_registry("observe_wildcard")
    assert "observe_wildcard" in specs
    spec = specs["observe_wildcard"]
    assert {n.id for n in spec.nodes} == {"observe_wildcard_handler"}
    bundle = compile_spec(spec, sub_registry=specs)
    assert bundle.spec_id == "observe_wildcard"


# ---------------------------------------------------------------------------
# (2) provider — default wildcard verdict=allow
# ---------------------------------------------------------------------------


def test_lca_observe_wildcard_provider_default_allow() -> None:
    from agent_lab.adapters.lca_control_act import LcaControlObserveWildcardProvider

    provider = LcaControlObserveWildcardProvider.from_node_config({})
    out = provider.emit(event_type="wildcard")
    assert "wildcard_event" in out
    result = out["wildcard_event"]
    assert result.kind == ArtifactKind.FACT
    assert result.schema_ref == "observe.wildcard.v1"
    assert result.content["verdict"] == "allow"
    assert result.content["event_type"] == "wildcard"


# ---------------------------------------------------------------------------
# (3) provider — with fixture callable (deny)
# ---------------------------------------------------------------------------


def test_lca_observe_wildcard_provider_with_fixture() -> None:
    from agent_lab.adapters.lca_control_act import (
        LcaControlObserveWildcardProvider,
        register_fixture_observe_wildcard,
        unregister_fixture_observe_wildcard,
    )

    name = "test-obs-wildcard-fixture"

    def _deny(event):
        return {"verdict": "deny", "reason": "wildcard-fixture-says-deny"}

    register_fixture_observe_wildcard(name, _deny)
    try:
        provider = LcaControlObserveWildcardProvider.from_node_config(
            {"provider_config": {"fixture_name": name}}
        )
        out = provider.emit(event_type="custom_event")
        result = out["wildcard_event"]
        assert result.content["verdict"] == "deny"
        assert result.content["reason"] == "wildcard-fixture-says-deny"
    finally:
        unregister_fixture_observe_wildcard(name)


# ---------------------------------------------------------------------------
# (4) runner integration
# ---------------------------------------------------------------------------


def test_observe_wildcard_subgraph_runs_via_runner() -> None:
    from agent_lab.adapters.lca_control_act import (
        register_fixture_observe_wildcard,
        unregister_fixture_observe_wildcard,
    )
    from agent_lab.runtime.runner import run as run_graph

    specs = load_registry("observe_wildcard")
    spec = specs["observe_wildcard"]
    fixture_name = "test-obs-wildcard-runner-fixture"

    def _allow_with_marker(event):
        return {"verdict": "allow", "marker": "runner-ok"}

    register_fixture_observe_wildcard(fixture_name, _allow_with_marker)
    try:
        for n in spec.nodes:
            if n.id == "observe_wildcard_handler":
                n.config["provider_config"] = {"fixture_name": fixture_name}

        initial = {
            "in_event": Artifact(
                kind=ArtifactKind.FACT,
                content={"phase": "stop", "ts": 1},
                schema_ref="event.wildcard.v1",
            ),
        }
        trace = run_graph(spec, initial=initial, sub_registry=specs)
        assert "wildcard_event" in trace.final_artifacts, (
            f"observe_wildcard must emit wildcard_event; "
            f"got {sorted(trace.final_artifacts)}"
        )
        result = trace.final_artifacts["wildcard_event"]
        assert result.kind == ArtifactKind.FACT
        assert result.content["verdict"] == "allow"
        assert result.content["marker"] == "runner-ok"
    finally:
        unregister_fixture_observe_wildcard(fixture_name)
