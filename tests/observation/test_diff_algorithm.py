"""diagnosis.diff algorithm tests —— 纯函数,deterministic."""

from __future__ import annotations

from lca.plugins.diagnosis.blueprint_trajectory_differ.plugin import (
    diff_blueprint_trajectory,
)
from tests.observation.conftest import (
    make_blueprint,
    make_exit,
)


def test_diff_marks_missing_node() -> None:
    bp = make_blueprint()
    exits = [make_exit("perceive.main", "perceive"), make_exit("act.main", "act")]
    diff = diff_blueprint_trajectory(run_id="r", blueprint=bp, node_exits=exits)
    missing_ids = [m.node_id for m in diff.missing_nodes]
    assert "think.main" in missing_ids
    assert "perceive.main" not in missing_ids


def test_diff_marks_unexpected_node() -> None:
    bp = make_blueprint(node_ids=("perceive.main",))
    exits = [make_exit("ghost.main", "perceive")]
    diff = diff_blueprint_trajectory(run_id="r", blueprint=bp, node_exits=exits)
    unexpected = [u.node_id for u in diff.unexpected_nodes]
    assert "ghost.main" in unexpected


def test_diff_flags_act_decision_missing() -> None:
    bp = make_blueprint()
    exits = [
        make_exit("perceive.main", "perceive"),
        make_exit("think.main", "think", outputs={"decision": {"action_type": "use_TOOL"}}),
        make_exit("act.main", "act", outputs={"decision": None}),
    ]
    diff = diff_blueprint_trajectory(run_id="r", blueprint=bp, node_exits=exits)
    assert any(v.node_id == "act.main" for v in diff.contract_violations)


def test_diff_flags_think_decision_missing() -> None:
    bp = make_blueprint()
    exits = [
        make_exit("perceive.main", "perceive"),
        make_exit("think.main", "think", outputs={"decision": None}),
        make_exit("act.main", "act"),
    ]
    diff = diff_blueprint_trajectory(run_id="r", blueprint=bp, node_exits=exits)
    assert any(v.node_id == "think.main" for v in diff.contract_violations)


def test_diff_clean_when_all_outputs_present() -> None:
    bp = make_blueprint()
    exits = [
        make_exit("perceive.main", "perceive"),
        make_exit("think.main", "think", outputs={"decision": {"action_type": "use_TOOL"}}),
        make_exit("act.main", "act", outputs={"decision": {"action_type": "use_TOOL"}}),
    ]
    diff = diff_blueprint_trajectory(run_id="r", blueprint=bp, node_exits=exits)
    assert diff.missing_nodes == ()
    assert diff.contract_violations == ()


def test_diff_pure_no_side_effects() -> None:
    """同输入两次调用 = 同结构性输出(diffed_at 是时间戳,ignore)。"""
    bp = make_blueprint()
    exits = [make_exit("perceive.main", "perceive")]
    d1 = diff_blueprint_trajectory(run_id="r", blueprint=bp, node_exits=exits)
    d2 = diff_blueprint_trajectory(run_id="r", blueprint=bp, node_exits=exits)
    d1_dict = d1.model_dump()
    d2_dict = d2.model_dump()
    d1_dict.pop("diffed_at", None)
    d2_dict.pop("diffed_at", None)
    assert d1_dict == d2_dict
    assert len(d1.missing_nodes) == len(d2.missing_nodes)
