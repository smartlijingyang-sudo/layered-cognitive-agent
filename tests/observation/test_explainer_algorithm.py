"""diagnosis.explainer algorithm tests —— 纯函数 + 模板表。"""

from __future__ import annotations

from lca.plugins.diagnosis.blueprint_trajectory_differ.plugin import (
    diff_blueprint_trajectory,
)
from lca.plugins.diagnosis.failure_explainer.plugin import (
    ROOT_CAUSE_TEMPLATES,
    explain_failure,
)
from tests.observation.conftest import (
    make_exit,
)


def test_explainer_h6_full_chain(blueprint_three_phase, h6_exit_set, h6_control_set) -> None:
    diff = diff_blueprint_trajectory(
        run_id="r", blueprint=blueprint_three_phase, node_exits=h6_exit_set
    )
    explanation = explain_failure(run_id="r", diff=diff, control_traces=h6_control_set)
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
    explanation = explain_failure(run_id="r", diff=diff, control_traces=[])
    assert explanation.outcome == "success"
    assert explanation.root_cause_chain == ()


def test_explainer_includes_remediation_hints_on_failure(
    blueprint_three_phase, h6_exit_set, h6_control_set
) -> None:
    diff = diff_blueprint_trajectory(
        run_id="r", blueprint=blueprint_three_phase, node_exits=h6_exit_set
    )
    explanation = explain_failure(run_id="r", diff=diff, control_traces=h6_control_set)
    assert len(explanation.remediation_hints) > 0
    has_command = any(h.command for h in explanation.remediation_hints)
    assert has_command, "remediation hints must include copy-paste-runnable commands"


def test_explainer_template_data_driven() -> None:
    """模板表是数据,可扩展。"""
    kinds = {t.kind for t in ROOT_CAUSE_TEMPLATES}
    assert "act_decision_missing" in kinds
    assert "node_never_entered" in kinds
    assert "control_unauthorized" in kinds
    assert "bundle_plugin_missing" in kinds
