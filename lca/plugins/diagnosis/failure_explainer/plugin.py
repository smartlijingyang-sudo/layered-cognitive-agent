"""diagnosis.failure_explainer —— 根因链生成(纯函数 + 模板表)。

module M8: lca/contracts/observability/observation/m8_explanation/

设计模式: 模板方法 + 数据驱动规则表。
  ROOT_CAUSE_TEMPLATES 是纯数据,每条规则 = (kind, evidence_fact_kind, statement_template, contract_clause)。
  算法 = 反向遍历 DiffReport + ControlTrace facts,匹规则表,产出 RootCauseStep 列表。

不是 LLM,不是 fuzzy match;纯 deterministic rule-based。可单测、可扩展、可固化 snapshot。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from lca.contracts.observability.observation import (
    ControlTrace,
    DiffReport,
    FailureExplanation,
    RemediationHint,
    RootCauseStep,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.loop.fact_gateway import append_surface_bound

_EV_EXPLANATION = "diagnosis.failure_explanation"
_OBSERVER_ACTOR = "diagnosis"


@dataclass(frozen=True)
class _Template:
    kind: str
    statement: str
    evidence_fact_kind: str | None = None
    contract_clause: str | None = None


# 根因规则表 —— 纯数据,可扩展。每条对应一类可解释失败。
ROOT_CAUSE_TEMPLATES: tuple[_Template, ...] = (
    _Template(
        "act_decision_missing",
        "act.main.results_by_phase[THINK].payload = None",
        evidence_fact_kind="NodeExit",
        contract_clause="art.action.action_type",
    ),
    _Template(
        "artifact_think_missing",
        "results_by_phase[THINK] = None",
        evidence_fact_kind="ArtifactSnapshot",
        contract_clause="art.think",
    ),
    _Template(
        "node_never_entered",
        "node 从未进入",
        evidence_fact_kind="NodeEnter",
        contract_clause="plan.node.enter",
    ),
    _Template(
        "subgraph_resolve_failed",
        "sub_spec_ref 解析失败",
        evidence_fact_kind="SubgraphResolve",
        contract_clause="subgraph.resolve",
    ),
    _Template(
        "bundle_plugin_missing",
        "bundle plugin 装载失败",
        evidence_fact_kind="BundleLoad",
        contract_clause="bundle.load",
    ),
    _Template(
        "control_unauthorized",
        "控制面 verdict=deny",
        evidence_fact_kind="ControlTrace",
        contract_clause="ctl.authorize",
    ),
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def explain_failure(
    *,
    run_id: str,
    diff: DiffReport,
    control_traces: Iterable[ControlTrace],
) -> FailureExplanation:
    """纯函数:diff + control traces → FailureExplanation(根因链 + 修复提示)。"""
    chain: list[RootCauseStep] = []
    hints: list[RemediationHint] = []
    step_idx = 0

    # 1. 控制面 deny → 第一根因节点
    for ctrl in control_traces:
        if ctrl.verdict != "deny":
            continue
        step_idx += 1
        chain.append(
            RootCauseStep(
                step_index=step_idx,
                statement=f"{ctrl.source_node_id}.control.{ctrl.control_slot} DENIED: {ctrl.reason or ''}".rstrip(
                    ": "
                ),
                evidence_fact_kind="ControlTrace",
                evidence_node_id=ctrl.source_node_id,
                contract_clause=ctrl.contract_clause or "ctl.authorize",
            )
        )
        hints.append(
            RemediationHint(
                hint=f"查看控制面为什么 deny {ctrl.source_node_id}",
                command=f"lca-ops trace show {run_id} --filter kind=control",
            )
        )

    # 2. 节点输出缺 decision → act 决策缺失
    for v in diff.contract_violations:
        if v.artifact_key != "decision":
            continue
        step_idx += 1
        chain.append(
            RootCauseStep(
                step_index=step_idx,
                statement=f"{v.node_id}.outputs.{v.artifact_key} = None",
                evidence_fact_kind="NodeExit",
                evidence_node_id=v.node_id,
                contract_clause=v.expected,
            )
        )
        hints.append(
            RemediationHint(
                hint=f"查看 {v.node_id} 的输入输出",
                command=f"lca-ops trace show {run_id} --node {v.node_id}",
            )
        )

    # 3. 节点缺失 → 根因往 plan 蓝图走
    for m in diff.missing_nodes:
        step_idx += 1
        chain.append(
            RootCauseStep(
                step_index=step_idx,
                statement=f"节点 {m.node_id} ({m.phase}) 期望执行但未执行",
                evidence_fact_kind="PlanBlueprint",
                evidence_node_id=m.node_id,
                contract_clause="plan.node.visit",
            )
        )
        hints.append(
            RemediationHint(
                hint="查看 plan 蓝图,确认节点绑定 / sub_spec_ref",
                command=f"lca-ops plan show {run_id}",
            )
        )

    summary = chain[0].statement if chain else "no failure detected"
    return FailureExplanation(
        run_id=run_id,
        outcome="failure" if chain else "success",
        summary=summary,
        root_cause_chain=tuple(chain),
        remediation_hints=tuple(hints),
        explained_at=_now_iso(),
    )


def observe_explanation(
    *,
    run_id: str,
    diff: DiffReport,
    control_traces: Iterable[ControlTrace],
) -> FailureExplanation:
    """Caller-facing wrapper:计算 + emit。"""
    explanation = explain_failure(run_id=run_id, diff=diff, control_traces=control_traces)
    append_surface_bound(
        _EV_EXPLANATION,
        explanation.model_dump(mode="json"),
        actor=_OBSERVER_ACTOR,
        surface_op="append",
        visibility="model",
    )
    return explanation


@plugin(
    id="diagnosis.failure_explainer",
    provides=("diagnosis.explainer",),
    requires=(),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description=(
        "Failure explanation —— 纯函数 + 模板表;从 DiffReport + ControlTrace 推根因链 + 修复提示。"
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    del config
    ctx.provide("diagnosis.explainer", observe_explanation)


__all__ = [
    "ROOT_CAUSE_TEMPLATES",
    "explain_failure",
    "observe_explanation",
    "setup",
]
