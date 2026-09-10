"""M8 — Failure explanation (根因链 + 修复提示).

Producer:  diagnosis.failure_explainer (纯函数 + 模板表)
Consumers: lca-ops run explain
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class RootCauseStep(BaseModel):
    """根因链上的一步:声明 + 证据 fact ref + 契约条款 ref。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    step_index: int
    statement: str  # 人读句:"act.main.inputs.decision = None"
    evidence_fact_kind: str | None = None  # NodeEnter / NodeExit / ...
    evidence_node_id: str | None = None
    contract_clause: str | None = None  # art.action.action_type / ...


class RemediationHint(BaseModel):
    """修复提示:agent 可直接调用的命令。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    hint: str
    command: str | None = None  # 精确指向下一步 CLI 命令


class FailureExplanation(BaseModel):
    """完整根因解释:summary + 根因链 + 修复提示。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    outcome: str  # success / failure
    broken_hop: str | None = None
    summary: str
    root_cause_chain: tuple[RootCauseStep, ...] = ()
    remediation_hints: tuple[RemediationHint, ...] = ()
    explained_at: str


__all__ = [
    "FailureExplanation",
    "RemediationHint",
    "RootCauseStep",
]
