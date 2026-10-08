"""diagnosis.failure_explainer —— 根因链生成(纯函数,3 个硬编码分支)。

module M8: lca/contracts/observability/observation/m8_explanation/

算法 = 3 个硬编码循环(不是模板表/规则引擎):
  1. control_traces 里 verdict=deny 的控制面拒绝 → 第一根因节点;
  2. diff.contract_violations 里 artifact_key == "decision" 的缺失 → act 决策缺失;
  3. diff.missing_nodes → 根因往 plan 蓝图走。

不是 LLM,不是 fuzzy match;纯 deterministic。可单测。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from lca.contracts.observability.observation import (
    ControlTrace,
    DiffReport,
    FailureExplanation,
    RemediationHint,
    RootCauseStep,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.loop.observation import now_iso, publish_ep_observation

_EV_EXPLANATION = "diagnosis.failure_explanation"


def explain_from_diff(
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
        explained_at=now_iso(),
    )


def observe_explanation(
    *,
    run_id: str,
    diff: DiffReport,
    control_traces: Iterable[ControlTrace],
) -> FailureExplanation:
    """Caller-facing wrapper:计算 + emit。"""
    explanation = explain_from_diff(run_id=run_id, diff=diff, control_traces=control_traces)
    publish_ep_observation(
        _EV_EXPLANATION,
        explanation.model_dump(mode="json"),
        actor="diagnosis",
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
        "Failure explanation —— 纯函数(3 个硬编码分支);从 DiffReport + ControlTrace 推根因链 + 修复提示。"
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    del config
    ctx.provide("diagnosis.explainer", observe_explanation)


__all__ = [
    "explain_from_diff",
    "observe_explanation",
    "setup",
]
