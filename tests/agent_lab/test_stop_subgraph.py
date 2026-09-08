"""stop_decide control-slot wiring + adapter + node tests.

Covers:
  - stop_decide.yaml loads + compiles without validation errors
  - LcaControlStopPolicyProvider default → NeverStop (should_stop=False)
  - Fixture policy → should_stop=True + terminal
  - stop_decide runs end-to-end through the runner
  - agent_loop attaches stop_decide on remember (not a peer phase host)
"""

from __future__ import annotations

import sys
from pathlib import Path

import agent_lab.nodes.control.stop_decide.plugin  # noqa: F401
from agent_lab.graph.compile import compile as compile_spec
from agent_lab.graphs import load_registry
from agent_lab.primitives.artifact import Artifact, ArtifactKind
from agent_lab.runtime.runner import run as run_graph

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def test_stop_decide_subgraph_loads_and_compiles() -> None:
    specs = load_registry("stop_decide")
    assert "stop_decide" in specs
    spec = specs["stop_decide"]
    assert {n.id for n in spec.nodes} == {"stop_decide_handler"}
    bundle = compile_spec(spec, sub_registry=specs)
    assert bundle.spec_id == "stop_decide"
    flat = {n for layer in bundle.layers for n in layer}
    assert "stop_decide_handler" in flat


def test_lca_control_stop_policy_provider_default_continue() -> None:
    """No fixture → default _NeverStop returns should_stop=False + terminal."""
    from agent_lab.adapters.lca_control import LcaControlStopPolicyProvider

    provider = LcaControlStopPolicyProvider.from_node_config({})
    out = provider.decide(
        state=Artifact(kind=ArtifactKind.FACT, content={"step": 0}),
        decision=None,
        observation=None,
        reflection=None,
    )
    assert "stop_decision" in out
    assert "terminal" in out
    sd = out["stop_decision"]
    assert sd.schema_ref == "stop_decision.v1"
    assert sd.content["should_stop"] is False
    assert out["terminal"].schema_ref == "terminal.v1"


def test_lca_control_stop_policy_provider_with_fixture() -> None:
    """Register a custom policy that returns should_stop=True."""
    from agent_lab.adapters.lca_control import (
        LcaControlStopPolicyProvider,
        register_fixture_stop_policy,
        unregister_fixture_stop_policy,
    )
    from lca.contracts.models.core.policy.stop import StopDecision, StopReason

    name = "test-stop-fixture"

    class _Halt:
        def decide(self, state, decision, observation, reflection):
            return StopDecision(
                should_stop=True,
                reason=StopReason.TASK_COMPLETED,
                final_output="done",
            )

    register_fixture_stop_policy(name, _Halt())
    try:
        provider = LcaControlStopPolicyProvider.from_node_config(
            {"provider_config": {"fixture_stop_policy_name": name}}
        )
        out = provider.decide(
            state=Artifact(kind=ArtifactKind.FACT, content={"step": 1}),
            decision=None,
        )
        sd = out["stop_decision"]
        assert sd.content["should_stop"] is True
        terminal = out["terminal"]
        assert terminal.schema_ref == "terminal.v1"
        assert terminal.content["stop_decision"]["should_stop"] is True
    finally:
        unregister_fixture_stop_policy(name)


def test_stop_decide_subgraph_runs_via_runner() -> None:
    """The stop_decide control graph runs end-to-end through the runner."""
    from agent_lab.adapters.lca_control import (
        register_fixture_stop_policy,
        unregister_fixture_stop_policy,
    )
    from lca.contracts.models.core.policy.stop import StopDecision, StopReason

    specs = load_registry("stop_decide")
    stop_spec = specs["stop_decide"]
    fixture_name = "test-stop-runner-fixture"

    class _Halt:
        def decide(self, state, decision, observation, reflection):
            return StopDecision(
                should_stop=True,
                reason=StopReason.TASK_COMPLETED,
                final_output="done",
            )

    register_fixture_stop_policy(fixture_name, _Halt())
    try:
        for n in stop_spec.nodes:
            if n.id == "stop_decide_handler":
                n.config["provider_config"] = {
                    "fixture_stop_policy_name": fixture_name
                }
        initial = {
            "in_state": Artifact(kind=ArtifactKind.FACT, content={"step": 2}),
            "in_decision": Artifact(
                kind=ArtifactKind.FACT,
                content={"decision_id": "d1", "action_type": "respond"},
            ),
        }
        trace = run_graph(stop_spec, initial=initial, sub_registry=specs)
        assert "stop_decision" in trace.final_artifacts, (
            f"stop_decide must emit stop_decision; got {sorted(trace.final_artifacts)}"
        )
        sd = trace.final_artifacts["stop_decision"]
        assert sd.content["should_stop"] is True
        assert "terminal" in trace.final_artifacts
        terminal = trace.final_artifacts["terminal"]
        assert terminal.schema_ref == "terminal.v1"
    finally:
        unregister_fixture_stop_policy(fixture_name)


def test_agent_loop_attaches_stop_control_on_remember() -> None:
    """stop_decide / stop_focus are control siblings of remember, not a stop host."""
    from agent_lab.plugins.control_slots import ControlSlotsPlugin

    specs = load_registry(
        "perceive",
        "think",
        "reflect",
        "remember",
        "model_eye",
        "act",
        "agent_loop",
    )
    plugin = ControlSlotsPlugin(name="control_slots", kind="control_slots")
    mutated = plugin.before_compile(specs["agent_loop"], specs)
    host_ids = {n.id for n in mutated.nodes}
    assert "stop" not in host_ids
    assert "remember" in host_ids

    remember = next(n for n in mutated.nodes if n.id == "remember")
    for port_name in ("stop_decision", "terminal", "focus_verdict"):
        assert port_name in remember.outs, (
            f"remember host missing stop control port {port_name}; has {remember.outs}"
        )

    links = {(link.node_id, link.sub_spec_id) for link in mutated.sub_specs}
    assert ("remember", "stop_decide") in links
    assert ("remember", "stop_focus") in links
    assert not any(nid == "stop" for nid, _ in links)
