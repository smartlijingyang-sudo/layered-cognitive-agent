"""M6/M7/M8/M9 — ArtifactSnapshot + DiffReport + FailureExplanation + RunReplay contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lca.contracts.observability.observation import (
    ArtifactSnapshot,
    ContractViolation,
    DiffReport,
    EdgeDeviation,
    FailureExplanation,
    MissingNode,
    RemediationHint,
    ReplayDiffSummary,
    ReplayStep,
    RootCauseStep,
    RunReplay,
    UnexpectedNode,
)


def test_missing_node_with_expected_outputs() -> None:
    m = MissingNode(
        node_id="think.main",
        phase="think",
        expected_outputs=("decision",),
    )
    assert m.expected_outputs == ("decision",)


def test_unexpected_node_signals_framework_bug() -> None:
    u = UnexpectedNode(node_id="ghost.main", phase="perceive")
    assert u.node_id == "ghost.main"


def test_contract_violation_carries_observed() -> None:
    v = ContractViolation(
        node_id="act.main",
        artifact_key="decision",
        expected="action_type ∈ granted",
        observed={"decision": None},
    )
    assert v.observed == {"decision": None}


def test_edge_deviation_marks_unexpected_edge() -> None:
    e = EdgeDeviation(
        source_node="perceive.main",
        expected_target="think.main",
        actual_target="act.main",
        deviation_kind="unexpected_edge",
    )
    assert e.actual_target == "act.main"


def test_diff_report_empty_when_clean() -> None:
    d = DiffReport(run_id="r", plan_ref="p", diffed_at="t")
    assert d.missing_nodes == ()
    assert d.contract_violations == ()


def test_root_cause_step_links_evidence_and_clause() -> None:
    s = RootCauseStep(
        step_index=1,
        statement="act.main.control.act.authorize DENIED",
        evidence_fact_kind="ControlTrace",
        evidence_node_id="act.main",
        contract_clause="art.action.action_type",
    )
    assert s.contract_clause == "art.action.action_type"


def test_remediation_hint_carries_command() -> None:
    h = RemediationHint(
        hint="查看控制面",
        command="lca-ops observation trace-show r --filter kind=control",
    )
    assert h.command is not None


def test_failure_explanation_minimal_success() -> None:
    e = FailureExplanation(
        run_id="r",
        outcome="success",
        summary="ok",
        explained_at="t",
    )
    assert e.root_cause_chain == ()


def test_artifact_snapshot_carries_full_artifacts() -> None:
    a = ArtifactSnapshot(
        run_id="r",
        node_id="think.main",
        phase="think",
        artifacts={"decision": {"action_type": "use_TOOL"}, "observation": {}},
        snapshotted_at="t",
    )
    assert a.artifacts["decision"]["action_type"] == "use_TOOL"


def test_replay_step_status_visited() -> None:
    s = ReplayStep(
        step=1,
        node_id="perceive.main",
        phase="perceive",
        status="visited",
        inputs={"x": 1},
        outputs={"y": 2},
    )
    assert s.status == "visited"


def test_replay_diff_summary_first_failure() -> None:
    s = ReplayDiffSummary(
        nodes_total=6,
        nodes_visited=("perceive.main",),
        nodes_missing=("think.main",),
        first_failure_node="act.main",
    )
    assert s.first_failure_node == "act.main"


def test_run_replay_smoke() -> None:
    r = RunReplay(
        run_id="r",
        plan_ref="p",
        replay_steps=(),
        diff_summary=ReplayDiffSummary(),
        replayed_at="t",
    )
    assert r.plan_ref == "p"


def test_failure_explanation_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        FailureExplanation(
            run_id="r",
            outcome="success",
            summary="x",
            explained_at="t",
            unknown="nope",  # type: ignore[call-arg]
        )
