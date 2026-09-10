"""M7 — Diff report (期望 vs 实际).

Producer:  diagnosis.blueprint_trajectory_differ (纯函数)
Consumers: lca-ops run explain, diagnosis.failure_explainer
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class MissingNode(BaseModel):
    """期望但未执行的节点。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str
    phase: str
    expected_outputs: tuple[str, ...] = ()


class UnexpectedNode(BaseModel):
    """实际执行但蓝图未声明的节点(框架 bug 信号)。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str
    phase: str


class ContractViolation(BaseModel):
    """契约违反:具体 artifact 字段不符合预期。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str
    artifact_key: str  # decision / observation / reflection / degradation
    expected: str
    observed: dict[str, Any] | None = None


class EdgeDeviation(BaseModel):
    """边偏差:走了不该走的边 / 没走该走的边。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_node: str
    expected_target: str | None = None
    actual_target: str | None = None
    deviation_kind: str  # missing_edge / unexpected_edge


class DiffReport(BaseModel):
    """完整 diff:missing + unexpected + 契约违反 + 边偏差。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    plan_ref: str
    missing_nodes: tuple[MissingNode, ...] = ()
    unexpected_nodes: tuple[UnexpectedNode, ...] = ()
    contract_violations: tuple[ContractViolation, ...] = ()
    edge_deviations: tuple[EdgeDeviation, ...] = ()
    diffed_at: str


__all__ = [
    "ContractViolation",
    "DiffReport",
    "EdgeDeviation",
    "MissingNode",
    "UnexpectedNode",
]
