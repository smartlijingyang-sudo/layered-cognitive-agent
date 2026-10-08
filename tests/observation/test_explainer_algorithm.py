"""diagnosis.explainer algorithm tests —— 纯函数，3 个硬编码分支（RA-035）。"""

from __future__ import annotations

from lca.plugins.diagnosis.blueprint_trajectory_differ.plugin import (
    diff_blueprint_trajectory,
)
from lca.plugins.diagnosis.failure_explainer.plugin import (
    explain_from_diff,
)
from tests.observation.conftest import (
    make_exit,
)


def test_explainer_h6_full_chain(blueprint_three_phase, h6_exit_set, h6_control_set) -> None:
    diff = diff_blueprint_trajectory(
        run_id="r", blueprint=blueprint_three_phase, node_exits=h6_exit_set
    )
    explanation = explain_from_diff(run_id="r", diff=diff, control_traces=h6_control_set)
    assert explanation.outcome == "failure"
    statements = " ".join(s.statement for s in explanation.root_cause_chain)
    assert "DENIED" in statements
    assert "think.main" in statements
    assert explanation.summary != ""


def test_explainer_clean_when_all_pass(blueprint_three_phase) -> None:
    exits = [
        make_exit("perceive.main", "perceive"),
        make_exit("think.main", "think", outputs={"decision": {"action_type": "use_TOOL"}}),
        make_exit("act.main", "act", outputs={"decision": {"action_type": "use_TOOL"}}),
    ]
    diff = diff_blueprint_trajectory(run_id="r", blueprint=blueprint_three_phase, node_exits=exits)
    explanation = explain_from_diff(run_id="r", diff=diff, control_traces=[])
    assert explanation.outcome == "success"
    assert explanation.root_cause_chain == ()


def test_explainer_includes_remediation_hints_on_failure(
    blueprint_three_phase, h6_exit_set, h6_control_set
) -> None:
    diff = diff_blueprint_trajectory(
        run_id="r", blueprint=blueprint_three_phase, node_exits=h6_exit_set
    )
    explanation = explain_from_diff(run_id="r", diff=diff, control_traces=h6_control_set)
    assert len(explanation.remediation_hints) > 0
    has_command = any(h.command for h in explanation.remediation_hints)
    assert has_command, "remediation hints must include copy-paste-runnable commands"


def test_explainer_three_hardcoded_branches(
    blueprint_three_phase, h6_exit_set, h6_control_set
) -> None:
    """RA-035: 算法是 3 个硬编码循环，不是模板表 —— pin 住分支与顺序。

    h6 fixtures 同时触发全部三个分支：control deny（act.main 被拒）→
    decision 缺失（act.main outputs.decision=None）→ 节点缺失
    （think.main 从未进入）。
    """
    diff = diff_blueprint_trajectory(
        run_id="r", blueprint=blueprint_three_phase, node_exits=h6_exit_set
    )
    explanation = explain_from_diff(run_id="r", diff=diff, control_traces=h6_control_set)
    kinds = [s.evidence_fact_kind for s in explanation.root_cause_chain]
    assert kinds == ["ControlTrace", "NodeExit", "PlanBlueprint"]
    assert [s.step_index for s in explanation.root_cause_chain] == [1, 2, 3]
