"""diagnosis.run_replay algorithm tests —— pure fold."""

from __future__ import annotations

from lca.plugins.diagnosis.run_replay.plugin import build_run_replay
from tests.observation.conftest import (
    make_control,
    make_decision,
    make_enter,
    make_exit,
)


def test_replay_marks_missing_nodes(blueprint_three_phase) -> None:
    exits = [make_exit("perceive.main", "perceive")]
    replay = build_run_replay(
        run_id="r",
        blueprint=blueprint_three_phase,
        node_enters=[],
        node_exits=exits,
        decision_traces=[],
        control_traces=[],
        tool_calls=[],
        llm_calls=[],
    )
    missing = list(replay.diff_summary.nodes_missing)
    visited = list(replay.diff_summary.nodes_visited)
    assert "think.main" in missing
    assert "act.main" in missing
    assert "perceive.main" in visited


def test_replay_carries_inputs_outputs(blueprint_three_phase) -> None:
    enter = make_enter("perceive.main", "perceive", inputs={"user_text": "hi"})
    exit_obj = make_exit("perceive.main", "perceive", outputs={"context": {"user_text": "hi"}})
    replay = build_run_replay(
        run_id="r",
        blueprint=blueprint_three_phase,
        node_enters=[enter],
        node_exits=[exit_obj],
        decision_traces=[],
        control_traces=[],
        tool_calls=[],
        llm_calls=[],
    )
    step = next(s for s in replay.replay_steps if s.node_id == "perceive.main")
    assert step.inputs["user_text"] == "hi"
    assert step.outputs["context"]["user_text"] == "hi"


def test_replay_first_failure_on_control_deny(blueprint_three_phase) -> None:
    exits = [
        make_exit("perceive.main", "perceive"),
        make_exit("act.main", "act"),
    ]
    ctrls = [make_control("act.main", verdict="deny", reason="x")]
    replay = build_run_replay(
        run_id="r",
        blueprint=blueprint_three_phase,
        node_enters=[],
        node_exits=exits,
        decision_traces=[],
        control_traces=ctrls,
        tool_calls=[],
        llm_calls=[],
    )
    assert replay.diff_summary.first_failure_node == "act.main"


def test_replay_includes_decisions(blueprint_three_phase) -> None:
    exits = [make_exit("think.main", "think")]
    decisions = [make_decision("think.main", accepted=True, action_type="use_TOOL")]
    replay = build_run_replay(
        run_id="r",
        blueprint=blueprint_three_phase,
        node_enters=[],
        node_exits=exits,
        decision_traces=decisions,
        control_traces=[],
        tool_calls=[],
        llm_calls=[],
    )
    step = next(s for s in replay.replay_steps if s.node_id == "think.main")
    assert step.decision is not None
    assert step.decision["action_type"] == "use_TOOL"


def test_replay_pure_same_input_same_output(blueprint_three_phase) -> None:
    exits = [make_exit("perceive.main", "perceive")]
    r1 = build_run_replay(
        run_id="r",
        blueprint=blueprint_three_phase,
        node_enters=[],
        node_exits=exits,
        decision_traces=[],
        control_traces=[],
        tool_calls=[],
        llm_calls=[],
    )
    r2 = build_run_replay(
        run_id="r",
        blueprint=blueprint_three_phase,
        node_enters=[],
        node_exits=exits,
        decision_traces=[],
        control_traces=[],
        tool_calls=[],
        llm_calls=[],
    )
    r1_dict = r1.model_dump()
    r2_dict = r2.model_dump()
    r1_dict.pop("replayed_at", None)
    r2_dict.pop("replayed_at", None)
    assert r1_dict == r2_dict
    assert len(r1.replay_steps) == len(r2.replay_steps)
