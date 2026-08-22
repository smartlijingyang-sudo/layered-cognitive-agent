from __future__ import annotations

import pytest

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.enums import ActionType, ReflectionVerdict
from lca.contracts.models.core.budget import create_budget
from lca.contracts.models.core.decision import Decision, Observation, Reflection, ToolCall
from lca.contracts.models.core.gate_policy import GateDecided, PolicyFact
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.perceive_state import PerceiveState
from lca.contracts.models.core.state import AgentState
from lca.harness.profile.control_plan_resolver import project_control_plan
from lca.harness.profile.resolve import resolve_profile
from lca.layer2_runtime.control_policies import (
    ControlPolicyContext,
    DefaultControlPolicyEngine,
)
from lca.layer2_runtime.control_runtime import (
    ControlVerdictKind,
    aggregate_control_verdicts,
    select_control_entries,
)


def _state(*, max_steps: int = 4, used_steps: int = 0) -> AgentState:
    state = AgentState(
        trace_id="trace-control",
        task="control test",
        budget=create_budget(max_steps=max_steps),
    )
    state.budget.used_steps = used_steps
    return state


def _decision(
    *,
    action: ActionType | str = ActionType.RESPOND,
    tool_calls: list[ToolCall] | None = None,
) -> Decision:
    return Decision(
        decision_id="decision-control",
        action_type=action,
        rationale="test",
        confidence=1.0,
        tool_calls=tool_calls or [],
        response_text="ok",
    )


def _reflection() -> Reflection:
    return Reflection(
        reflection_id="reflection-control",
        verdict=ReflectionVerdict.ON_TRACK,
    )


def _observation() -> Observation:
    return Observation(observation_id="observation-control", success=True, payload="ok")


@pytest.fixture
def engine() -> DefaultControlPolicyEngine:
    return DefaultControlPolicyEngine()


@pytest.fixture
def plan():
    return project_control_plan(resolve_profile("profiles/web-standard.yaml"))


def _verdict(
    engine: DefaultControlPolicyEngine,
    plan,
    slot: ControlSlot,
    context: ControlPolicyContext,
):
    selection = select_control_entries(plan, slot, context.state)
    verdicts = engine.evaluate(selection, context)
    assert len(verdicts) == len(selection.entries) == 1 or slot is ControlSlot.THINK_GUARD
    return verdicts[0]


@pytest.mark.parametrize(
    "slot",
    (
        ControlSlot.PERCEIVE_CONTEXT,
        ControlSlot.THINK_GUARD,
        ControlSlot.ACT_AUTHORIZE,
        ControlSlot.ACT_BUDGET,
        ControlSlot.ACT_CONSTRAIN,
        ControlSlot.ACT_EXECUTE,
        ControlSlot.ACT_SAFE_BOUNDARY,
        ControlSlot.REMEMBER_ADMIT,
        ControlSlot.STOP_DECIDE,
        ControlSlot.OBSERVE_CHECKPOINT,
        ControlSlot.OBSERVE_WILDCARD,
    ),
)
def test_standard_profile_has_a_concrete_policy_for_every_slot(plan, slot: ControlSlot) -> None:
    selection = select_control_entries(plan, slot, _state())
    assert selection.entries
    assert all(not entry.plugin_id.startswith("control.default.") for entry in selection.entries)


def test_perceive_context_stops_non_working_run(engine: DefaultControlPolicyEngine, plan) -> None:
    state = _state()
    state.status = TaskStatus.FAILED

    verdict = _verdict(
        engine, plan, ControlSlot.PERCEIVE_CONTEXT, ControlPolicyContext(state=state)
    )

    assert verdict.kind is ControlVerdictKind.STOP


def test_think_guard_projects_recorded_gate_rewrite(
    engine: DefaultControlPolicyEngine, plan
) -> None:
    state = _state()
    view = PerceiveState.from_agent_state(state)
    view.gate_decided.append(
        GateDecided(
            event_id="gate-loop-break",
            gate="ToolLoopBreakerGate",
            verdict="rewrite",
            is_rewritten=True,
            rationale="tool loop break",
            policy_fact=PolicyFact(
                kind="tool_loop_break",
                message="stop retrying",
                source="tool_loop_breaker",
            ),
        )
    )
    view.commit(state)
    context = ControlPolicyContext(state=state, decision=_decision())
    selection = select_control_entries(plan, ControlSlot.THINK_GUARD, state)

    evaluation = aggregate_control_verdicts(selection, engine.evaluate(selection, context))

    assert [verdict.kind for verdict in evaluation.verdicts] == [
        ControlVerdictKind.ALLOW,
        ControlVerdictKind.REWRITE,
    ]
    assert evaluation.effective is not None
    assert evaluation.effective.kind is ControlVerdictKind.REWRITE


def test_authorize_denies_malformed_tool_action(engine: DefaultControlPolicyEngine, plan) -> None:
    verdict = _verdict(
        engine,
        plan,
        ControlSlot.ACT_AUTHORIZE,
        ControlPolicyContext(state=_state(), decision=_decision(action=ActionType.USE_TOOL)),
    )

    assert verdict.kind is ControlVerdictKind.DENY


def test_budget_reports_exhaustion(engine: DefaultControlPolicyEngine, plan) -> None:
    verdict = _verdict(
        engine,
        plan,
        ControlSlot.ACT_BUDGET,
        ControlPolicyContext(state=_state(max_steps=0, used_steps=1), decision=_decision()),
    )

    assert verdict.kind is ControlVerdictKind.EXHAUSTED


def test_constrain_denies_duplicate_tool_call_ids(engine: DefaultControlPolicyEngine, plan) -> None:
    calls = [
        ToolCall(call_id="same", tool_name="one", arguments={}),
        ToolCall(call_id="same", tool_name="two", arguments={}),
    ]
    verdict = _verdict(
        engine,
        plan,
        ControlSlot.ACT_CONSTRAIN,
        ControlPolicyContext(
            state=_state(),
            decision=_decision(action=ActionType.USE_TOOL, tool_calls=calls),
        ),
    )

    assert verdict.kind is ControlVerdictKind.DENY


def test_execute_denies_tool_action_without_call(engine: DefaultControlPolicyEngine, plan) -> None:
    verdict = _verdict(
        engine,
        plan,
        ControlSlot.ACT_EXECUTE,
        ControlPolicyContext(state=_state(), decision=_decision(action=ActionType.USE_TOOL)),
    )

    assert verdict.kind is ControlVerdictKind.DENY


def test_safe_boundary_stops_explicit_stop_decision(
    engine: DefaultControlPolicyEngine, plan
) -> None:
    verdict = _verdict(
        engine,
        plan,
        ControlSlot.ACT_SAFE_BOUNDARY,
        ControlPolicyContext(state=_state(), decision=_decision(action=ActionType.STOP)),
    )

    assert verdict.kind is ControlVerdictKind.STOP


def test_remember_requires_complete_turn(engine: DefaultControlPolicyEngine, plan) -> None:
    denied = _verdict(
        engine,
        plan,
        ControlSlot.REMEMBER_ADMIT,
        ControlPolicyContext(state=_state(), observation=_observation()),
    )
    allowed = _verdict(
        engine,
        plan,
        ControlSlot.REMEMBER_ADMIT,
        ControlPolicyContext(
            state=_state(),
            observation=_observation(),
            reflection=_reflection(),
        ),
    )

    assert denied.kind is ControlVerdictKind.DENY
    assert allowed.kind is ControlVerdictKind.ALLOW


def test_stop_decide_stops_exhausted_budget(engine: DefaultControlPolicyEngine, plan) -> None:
    verdict = _verdict(
        engine,
        plan,
        ControlSlot.STOP_DECIDE,
        ControlPolicyContext(state=_state(max_steps=0, used_steps=1)),
    )

    assert verdict.kind is ControlVerdictKind.STOP


def test_observe_slots_emit_concrete_allow_verdicts(
    engine: DefaultControlPolicyEngine, plan
) -> None:
    state = _state()
    checkpoint = _verdict(
        engine,
        plan,
        ControlSlot.OBSERVE_CHECKPOINT,
        ControlPolicyContext(state=state),
    )
    wildcard = _verdict(
        engine,
        plan,
        ControlSlot.OBSERVE_WILDCARD,
        ControlPolicyContext(state=state),
    )

    assert checkpoint.kind is ControlVerdictKind.ALLOW
    assert wildcard.kind is ControlVerdictKind.ALLOW
