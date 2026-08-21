"""Reducer / LoopTopology contract tests (ADR-0066).

Pure-function tests on the Reducer Protocol default implementation.
"""

from __future__ import annotations

from lca.contracts.models.core.activation import ActivatedSkill
from lca.contracts.models.core.budget import create_budget
from lca.contracts.models.core.decision import Decision, Observation, Reflection, Turn
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.perception import ContextItem, ContextManifest
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.core.stop import StopDecision
from lca.layer2_runtime.loop_topology import ClosedSetTopology
from lca.layer2_runtime.reducer import DefaultReducer


def _state() -> AgentState:
    return AgentState(
        trace_id="trace-1",
        task="t",
        budget=create_budget(max_steps=10),
    )


def test_apply_step_advanced_updates_step_and_budget() -> None:
    state = _state()
    out = DefaultReducer().apply_step_advanced(state, 3)
    assert out.step == 3
    assert out.budget.used_steps == 3


def test_apply_perception_writes_manifest_digest() -> None:
    state = _state()
    manifest = ContextManifest(
        items=(ContextItem(kind="clock", payload="12:00", provenance="clock"),), digest="abc"
    )
    out = DefaultReducer().apply_perception(state, manifest)
    assert out.extra["manifest_digest"] == "abc"


def test_apply_turn_appends_history() -> None:
    state = _state()
    decision = Decision(
        decision_id="d1",
        action_type="respond",  # type: ignore[arg-type]
        rationale="",
        confidence=1.0,
    )
    observation = Observation(observation_id="o1", success=True, payload="ok")
    reflection = Reflection(reflection_id="r1", verdict="on_track")  # type: ignore[arg-type]
    turn = Turn(decision=decision, observation=observation, reflection=reflection)
    out = DefaultReducer().apply_turn(state, turn)
    assert len(out.history) == 1
    assert out.history[0] is turn


def test_apply_activation_no_op_on_empty() -> None:
    state = _state()
    out = DefaultReducer().apply_activation(state, ())
    assert out.activated_skills == state.activated_skills


def test_apply_activation_extends_skills() -> None:
    state = _state()
    activated = (ActivatedSkill(skill_id="s1", name="S1", activated_at_step=0),)
    out = DefaultReducer().apply_activation(state, activated)
    assert out.activated_skills == [activated[0]]


def test_apply_stop_writes_status_and_output() -> None:
    state = _state()
    stop = StopDecision(
        should_stop=True,
        reason="completed",  # type: ignore[arg-type]
        status=TaskStatus.COMPLETED,
        final_output="done",
    )
    out = DefaultReducer().apply_stop(state, stop)
    assert out.status == TaskStatus.COMPLETED
    assert out.final_output == "done"


def test_apply_error_marks_failed() -> None:
    state = _state()
    err = RuntimeError("boom")
    out = DefaultReducer().apply_error(state, err)
    assert out.status == TaskStatus.FAILED
    assert "boom" in (out.last_error or "")


def test_apply_paused_marks_input_required() -> None:
    state = _state()
    out = DefaultReducer().apply_paused(state, "snap-ref")
    assert out.status == TaskStatus.INPUT_REQUIRED


def test_closed_set_topology_has_six_phases_in_canonical_order() -> None:
    phases = ClosedSetTopology().phases()
    kinds = [p.kind.value for p in phases]
    assert kinds == ["perceive", "think", "act", "reflect", "remember", "stop"]


def test_closed_set_topology_seam_keys_use_before_after_convention() -> None:
    """Seam keys follow ``agent.before_<phase>`` / ``agent.after_<phase>``.

    HookEvent enum (used for hooks.trigger) uses ``pre_/post_`` and is a
    separate namespace; seam keys are the public extension-point contract.
    """
    phases = ClosedSetTopology().phases()
    perceive = phases[0]
    assert perceive.pre_hook == "agent.before_perceive"
    assert perceive.post_hook == "agent.after_perceive"
    reflect = phases[3]
    assert reflect.pre_hook == "agent.before_reflect"
    assert reflect.post_hook == "agent.after_reflect"


def test_closed_set_topology_remember_stop_have_no_seam_keys() -> None:
    phases = ClosedSetTopology().phases()
    remember = phases[4]
    assert remember.pre_hook is None
    assert remember.post_hook is None
    stop = phases[5]
    assert stop.pre_hook is None
    assert stop.post_hook is None
