"""diagnosis.blueprint_trajectory_differ —— 期望 vs 实际 diff(纯函数)。

module M7: lca/contracts/observability/observation/m7_diff/

纯函数契约:
  inputs:  blueprint: PlanBlueprint, trajectory_facts: list[NodeExit]
  outputs: DiffReport
不写文件、不读 runtime状态、不带时间/随机。
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from lca.contracts.observability.observation import (
    ContractViolation,
    DiffReport,
    MissingNode,
    NodeExit,
    PlanBlueprint,
    UnexpectedNode,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.loop.fact_gateway import append_surface_bound

_EV_DIFF = "diagnosis.diff_report"
_OBSERVER_ACTOR = "diagnosis"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def diff_blueprint_trajectory(
    *,
    run_id: str,
    blueprint: PlanBlueprint,
    node_exits: Iterable[NodeExit],
) -> DiffReport:
    """纯函数:输入蓝图 + 节点退出事实,产出 DiffReport。

    行为:
      missing_nodes      = 蓝图声明但未执行的节点
      unexpected_nodes   = 执行了但蓝图未声明的节点
      contract_violations = 节点退出但 outputs 缺关键字段
      edge_deviations    = 暂时占位(0 期不基于 edges 判定)
    """
    executed_ids = {exit.node_id for exit in node_exits}
    expected_ids = {node.id for node in blueprint.nodes}

    missing = tuple(
        MissingNode(
            node_id=node.id,
            phase=node.phase,
            expected_outputs=tuple(
                key
                for key in ("decision", "observation", "reflection", "degradation")
                if node.phase in ("think", "act", "reflect", "remember")
            ),
        )
        for node in blueprint.nodes
        if node.id not in executed_ids
    )
    unexpected = tuple(
        UnexpectedNode(node_id=node_id, phase=phase)
        for node_id, phase in ((e.node_id, e.phase) for e in node_exits)
        if node_id not in expected_ids
    )
    violations: list[ContractViolation] = []
    for exit in node_exits:
        outputs = exit.outputs or {}
        if exit.phase == "act":
            decision = outputs.get("decision")
            if decision is None:
                violations.append(
                    ContractViolation(
                        node_id=exit.node_id,
                        artifact_key="decision",
                        expected="decision.action_type ∈ actions_authorized",
                        observed=outputs,
                    )
                )
        elif exit.phase == "think" and outputs.get("decision") is None:
            violations.append(
                ContractViolation(
                    node_id=exit.node_id,
                    artifact_key="decision",
                    expected="think 产出 Decision",
                    observed=outputs,
                )
            )
    return DiffReport(
        run_id=run_id,
        plan_ref=blueprint.plan_ref,
        missing_nodes=missing,
        unexpected_nodes=unexpected,
        contract_violations=tuple(violations),
        edge_deviations=(),
        diffed_at=_now_iso(),
    )


def observe_diff(
    *,
    run_id: str,
    blueprint: PlanBlueprint,
    node_exits: Iterable[NodeExit],
) -> DiffReport:
    """Caller-facing wrapper:计算 + emit。"""
    report = diff_blueprint_trajectory(run_id=run_id, blueprint=blueprint, node_exits=node_exits)
    append_surface_bound(
        _EV_DIFF,
        report.model_dump(mode="json"),
        actor=_OBSERVER_ACTOR,
        surface_op="append",
        visibility="model",
    )
    return report


@plugin(
    id="diagnosis.blueprint_trajectory_differ",
    provides=("diagnosis.diff",),
    requires=(),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="Blueprint vs trajectory diff —— 纯函数,产出 DiffReport.",
)
async def setup(ctx: PluginContext, config: Any) -> None:
    del config
    ctx.provide("diagnosis.diff", observe_diff)


__all__ = ["diff_blueprint_trajectory", "observe_diff", "setup"]
