"""Control-slot sub-graph tests.

Covers:
  - All 4 control/* YAML specs load and compile without validation errors.
  - LcaControlDecisionGateProvider with a fixture DecisionGate.
  - LcaControlStopPolicyProvider with a fixture StopPolicy.
  - LcaControlCheckpointProvider default noop emits counter-stamped fact.
  - LcaControlRememberAdmitProvider with a fixture admit callable.
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


def test_control_slot_graphs_load_and_compile() -> None:
    """Load all 4 control/* specs and compile each — no validation errors."""
    r = load_registry("think_guard", "stop_decide", "observe_checkpoint", "remember_admit")
    assert set(r.keys()) == {"think_guard", "stop_decide", "observe_checkpoint", "remember_admit"}
    for name, spec in r.items():
        bundle = compile_spec(spec, sub_registry=r)
        assert bundle.spec_id == name


# ---------------------------------------------------------------------------
# (2) DecisionGate provider with fixture
# ---------------------------------------------------------------------------


def test_lca_control_decision_gate_provider_with_fixture() -> None:
    """Register a fixture gate, run think_guard_node, assert verdict."""
    from agent_lab.adapters.lca_control import (
        LcaControlDecisionGateProvider,
        register_fixture_decision_gate,
        unregister_fixture_decision_gate,
    )

    name = "test-ctrl-gate"

    class _RejectGate:
        async def enforce(self, state, decision):
            from lca.contracts.models.core.execution.decision import Decision

            return Decision(
                decision_id=getattr(decision, "decision_id", "dec_rejected"),
                action_type="refuse",
                rationale="gate rejected",
                confidence=0.2,
            )

    register_fixture_decision_gate(name, _RejectGate())
    try:
        provider = LcaControlDecisionGateProvider.from_node_config(
            {"provider_config": {"fixture_decision_gate_name": name}}
        )
        decision_artifact = Artifact(
            kind=ArtifactKind.FACT,
            content={
                "decision_id": "dec_in",
                "action_type": "respond",
                "rationale": "do something",
                "confidence": 1.0,
                "tool_calls": [],
            },
        )
        out = provider.enforce(decision_artifact=decision_artifact)
        assert "out_decision" in out
        result = out["out_decision"]
        assert result.kind == ArtifactKind.FACT
        assert result.content["action_type"] == "refuse"
        assert result.content["decision_id"] == "dec_in"
    finally:
        unregister_fixture_decision_gate(name)


# ---------------------------------------------------------------------------
# (3) StopPolicy provider with fixture
# ---------------------------------------------------------------------------


def test_lca_control_stop_policy_provider_with_fixture() -> None:
    """Register a fixture StopPolicy returning should_stop=True / BUDGET_EXCEEDED."""
    from agent_lab.adapters.lca_control import (
        LcaControlStopPolicyProvider,
        register_fixture_stop_policy,
        unregister_fixture_stop_policy,
    )
    from lca.contracts.models.core.policy.stop import StopDecision, StopReason

    name = "test-ctrl-stop"

    class _BudgetStop:
        def decide(self, state, decision, observation, reflection):
            return StopDecision(should_stop=True, reason=StopReason.BUDGET_EXCEEDED)

    register_fixture_stop_policy(name, _BudgetStop())
    try:
        provider = LcaControlStopPolicyProvider.from_node_config(
            {"provider_config": {"fixture_stop_policy_name": name}}
        )
        out = provider.decide()
        assert "stop_decision" in out
        result = out["stop_decision"]
        assert result.kind == ArtifactKind.FACT
        assert result.content["should_stop"] is True
        assert result.content["reason"] == "budget_exceeded"
    finally:
        unregister_fixture_stop_policy(name)


# ---------------------------------------------------------------------------
# (4) Checkpoint provider — default noop
# ---------------------------------------------------------------------------


def test_lca_control_checkpoint_provider_default() -> None:
    """No fixture: noop emits counter-stamped checkpoint fact."""
    from agent_lab.adapters.lca_control import LcaControlCheckpointProvider

    provider = LcaControlCheckpointProvider.from_node_config({})
    out = provider.emit(event_type="checkpoint")
    assert "checkpoint_event" in out
    result = out["checkpoint_event"]
    assert result.kind == ArtifactKind.FACT
    assert result.content["event_type"] == "checkpoint"
    assert "seq" in result.content
    assert isinstance(result.content["seq"], int)
    assert result.content["seq"] >= 1
    assert "ts" in result.content
    assert "fact_id" in result.content


# ---------------------------------------------------------------------------
# (5) Remember admit provider with fixture
# ---------------------------------------------------------------------------


def test_lca_control_remember_admit_provider_with_fixture() -> None:
    """Fixture admit callable rejects content=='reject_me'."""
    from agent_lab.adapters.lca_control import (
        LcaControlRememberAdmitProvider,
        register_fixture_remember_admit,
        unregister_fixture_remember_admit,
    )

    name = "test-ctrl-admit"

    def _admit(observation):
        raw = observation.content if isinstance(observation, Artifact) else observation
        content = (
            str(raw.get("content", "")) if isinstance(raw, dict) else (str(raw) if raw else "")
        )
        return content != "reject_me"

    register_fixture_remember_admit(name, _admit)
    try:
        provider = LcaControlRememberAdmitProvider.from_node_config(
            {"provider_config": {"fixture_remember_admit_name": name}}
        )
        # Should reject
        obs_reject = Artifact(
            kind=ArtifactKind.FACT,
            content={"content": "reject_me"},
        )
        out = provider.admit(observation=obs_reject)
        assert "admit_verdict" in out
        assert out["admit_verdict"].content["admitted"] is False

        # Should accept
        obs_accept = Artifact(
            kind=ArtifactKind.FACT,
            content={"content": "keep_me"},
        )
        out = provider.admit(observation=obs_accept)
        assert out["admit_verdict"].content["admitted"] is True
    finally:
        unregister_fixture_remember_admit(name)
