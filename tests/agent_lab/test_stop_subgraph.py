"""stop sub-graph wiring + adapter + node tests.

Covers:
  - stop.yaml loads + compiles without validation errors
  - LcaStopPolicyProvider default → ContinuePolicy (should_stop=False)
  - LcaStopPolicyProvider with fixture policy → custom StopDecision
  - Full sub-graph runs via agent_lab's runner
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the stop node is registered (since nodes/__init__.py may not
# import the stop subpackage yet).
import agent_lab.nodes.stop.evaluate_stop.plugin  # noqa: F401
from agent_lab.graph.compile import compile as compile_spec
from agent_lab.graphs import load_registry
from agent_lab.primitives.artifact import Artifact, ArtifactKind

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# (1) graph load + compile
# ---------------------------------------------------------------------------


def test_stop_subgraph_loads_and_compiles() -> None:
    specs = load_registry("stop")
    assert "stop" in specs
    spec = specs["stop"]
    assert {n.id for n in spec.nodes} == {"evaluate_stop"}
    bundle = compile_spec(spec, sub_registry=specs)
    assert bundle.spec_id == "stop"
    flat = [nid for layer in bundle.layers for nid in layer]
    assert "evaluate_stop" in flat


# ---------------------------------------------------------------------------
# (2) provider — default continue
# ---------------------------------------------------------------------------


def test_lca_stop_policy_provider_default_continue() -> None:
    """No fixture → default _ContinuePolicy returns should_stop=False."""
    from agent_lab.adapters.lca_stop import LcaStopPolicyProvider

    provider = LcaStopPolicyProvider.from_node_config({})
    out = provider.decide(
        state_artifact=Artifact(kind=ArtifactKind.FACT, content={"step": 1}),
        decision_artifact=Artifact(
            kind=ArtifactKind.FACT,
            content={"decision_id": "dec_1", "action_type": "respond"},
        ),
        observation_artifact=Artifact(kind=ArtifactKind.FACT, content={"tool_result": "ok"}),
        reflection_artifact=Artifact(kind=ArtifactKind.FACT, content={"self_eval": "fine"}),
    )
    assert "stop_decision" in out
    assert "terminal" in out
    sd = out["stop_decision"]
    assert sd.kind == ArtifactKind.FACT
    assert sd.schema_ref == "stop_decision.v1"
    assert sd.content["should_stop"] is False
    assert sd.content["reason"] == "continue"


# ---------------------------------------------------------------------------
# (3) provider — with fixture policy
# ---------------------------------------------------------------------------


def test_lca_stop_policy_provider_with_fixture() -> None:
    """Register a custom policy that returns should_stop=True."""
    from agent_lab.adapters.lca_stop import (
        LcaStopPolicyProvider,
        register_fixture_policy,
        unregister_fixture_policy,
    )
    from lca.contracts.models.core.policy.stop import StopDecision, StopReason

    name = "test-stop-fixture"

    class _CompletePolicy:
        def decide(self, state, decision, observation, reflection):
            return StopDecision(
                should_stop=True,
                reason=StopReason.TASK_COMPLETED,
                final_output="done",
                status=None,
                failure=None,
            )

    register_fixture_policy(name, _CompletePolicy())
    try:
        provider = LcaStopPolicyProvider.from_node_config(
            {"provider_config": {"fixture_policy_name": name}}
        )
        out = provider.decide(
            state_artifact=Artifact(kind=ArtifactKind.FACT, content={}),
            decision_artifact=Artifact(
                kind=ArtifactKind.FACT,
                content={"decision_id": "dec_1", "action_type": "respond"},
            ),
            observation_artifact=Artifact(kind=ArtifactKind.FACT, content={}),
            reflection_artifact=Artifact(kind=ArtifactKind.FACT, content={}),
        )
        sd = out["stop_decision"]
        assert sd.content["should_stop"] is True
        assert sd.content["reason"] == "task_completed"
        assert sd.content["final_output"] == "done"
        # Terminal also carries the stop_decision
        terminal = out["terminal"]
        assert terminal.schema_ref == "terminal.v1"
        assert terminal.content["stop_decision"]["should_stop"] is True
    finally:
        unregister_fixture_policy(name)


# ---------------------------------------------------------------------------
# (4) runner integration
# ---------------------------------------------------------------------------


def test_stop_subgraph_runs_via_runner() -> None:
    """The stop sub-graph runs end-to-end through agent_lab's runner."""
    from agent_lab.adapters.lca_stop import (
        register_fixture_policy,
        unregister_fixture_policy,
    )
    from agent_lab.runtime.runner import run as run_graph
    from lca.contracts.models.core.policy.stop import StopDecision, StopReason

    specs = load_registry("stop")
    stop_spec = specs["stop"]

    # Configure the evaluate_stop node to use a fixture policy.
    fixture_name = "test-stop-runner-fixture"

    class _RunnerPolicy:
        def decide(self, state, decision, observation, reflection):
            return StopDecision(
                should_stop=True,
                reason=StopReason.TASK_COMPLETED,
                final_output="task done",
                status=None,
                failure=None,
            )

    register_fixture_policy(fixture_name, _RunnerPolicy())
    try:
        # Point the node config at the fixture.
        for n in stop_spec.nodes:
            if n.id == "evaluate_stop":
                n.config["provider_config"] = {"fixture_policy_name": fixture_name}

        initial = {
            "in_decision": Artifact(
                kind=ArtifactKind.FACT,
                content={"decision_id": "dec_1", "action_type": "respond"},
                schema_ref="decision.v1",
            ),
            "in_observation": Artifact(
                kind=ArtifactKind.FACT,
                content={"tool_result": "ok"},
                schema_ref="observation.v1",
            ),
            "in_reflection": Artifact(
                kind=ArtifactKind.FACT,
                content={"self_eval": "fine"},
                schema_ref="reflection.v1",
            ),
            "in_state": Artifact(
                kind=ArtifactKind.FACT,
                content={"step": 3},
                schema_ref="state.v1",
            ),
        }
        trace = run_graph(stop_spec, initial=initial, sub_registry=specs)
        assert "stop_decision" in trace.final_artifacts, (
            f"stop sub-graph must emit stop_decision; got {sorted(trace.final_artifacts)}"
        )
        sd = trace.final_artifacts["stop_decision"]
        assert sd.kind == ArtifactKind.FACT
        assert sd.content["should_stop"] is True
        assert sd.content["reason"] == "task_completed"
        assert sd.content["final_output"] == "task done"
        assert "terminal" in trace.final_artifacts
        terminal = trace.final_artifacts["terminal"]
        assert terminal.schema_ref == "terminal.v1"
    finally:
        unregister_fixture_policy(fixture_name)
