"""Stop grace path when budget exhausted after delivery (ADR-0196 P3)."""

from __future__ import annotations

from lca.cognition.convergence.policy import DefaultConvergencePolicy
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.execution.decision import Decision, Observation, ToolCall, Turn
from lca.contracts.models.core.perceive.perception import ContextItem, ContextManifest
from lca.contracts.models.core.perceive.projection import PerceiveProjection
from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.plugins.loop.state.stop_policy.plugin import DefaultStopPolicy


class _EmptyArtifactClosure:
    def synthesize(self, *, fallback: str = "") -> str | None:
        return None


def _delivery_satisfied_state() -> AgentState:
    manifest = ContextManifest(
        digest="d",
        items=(
            ContextItem(
                kind="workspace_artifacts",
                payload=[{"path": "graphplan_joke.png", "url": "/files/file_abcd"}],
                provenance="sensor.workspace-artifacts",
            ),
        ),
    )
    state = AgentState(
        trace_id="t",
        task="用python写一个图计划的笑话",
        budget=Budget(max_steps=0, used_steps=1),
        perceive=PerceiveProjection(manifest=manifest, digest="d", step=1),
    )
    state.history.append(
        Turn(
            decision=Decision(
                decision_id="d0",
                action_type=ActionType.USE_TOOL,
                rationale="run",
                confidence=0.9,
                tool_calls=[ToolCall(call_id="c0", tool_name="executeCode", arguments={})],
            ),
            observation=Observation(observation_id="o0", success=True, payload={"ok": True}),
        )
    )
    return state


def test_policy_budget_exhausted_grace_when_delivery_satisfied() -> None:
    state = _delivery_satisfied_state()
    from lca.cognition.convergence.evidence import build_delivery_evidence

    evidence = build_delivery_evidence(state)
    assert evidence.satisfied is True
    verdict = DefaultConvergencePolicy().evaluate_budget_exhausted(state, evidence=evidence)
    assert verdict.kind == "grace_respond"


def test_stop_policy_grace_respond_on_budget_exhausted_with_delivery() -> None:
    policy = DefaultStopPolicy(_EmptyArtifactClosure())
    state = _delivery_satisfied_state()
    observation = Observation(observation_id="obs", success=False, payload=None)

    stop = policy.decide(state, None, observation, None)

    assert stop.should_stop is True
    assert stop.status == TaskStatus.COMPLETED
    assert stop.final_output is not None
    assert "工作区" in stop.final_output or len(stop.final_output) > 20
