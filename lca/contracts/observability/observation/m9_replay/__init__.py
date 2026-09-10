"""M9 — Run replay (时间序 steps 数组,agent 可 walk).

Producer:  diagnosis.run_replay (纯函数)
Consumers: lca-ops run replay
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ReplayStep(BaseModel):
    """单步 replay:节点 + 现场 + 控制/工具/LLM/决策 + 异常。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    step: int
    node_id: str | None = None
    phase: str | None = None
    binding: str | None = None
    status: str  # visited / missing / unexpected
    entered_at: str | None = None
    exited_at: str | None = None
    inputs: dict[str, Any] = {}
    outputs: dict[str, Any] = {}
    decision: dict[str, Any] | None = None
    control_verdicts: tuple[dict[str, Any], ...] = ()
    tool_calls: tuple[dict[str, Any], ...] = ()
    llm_calls: tuple[dict[str, Any], ...] = ()
    anomalies: tuple[str, ...] = ()


class ReplayDiffSummary(BaseModel):
    """replay 顶部的 diff 摘要:agent 先看这一段。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    nodes_total: int = 0
    nodes_visited: tuple[str, ...] = ()
    nodes_missing: tuple[str, ...] = ()
    first_failure_node: str | None = None


class RunReplay(BaseModel):
    """完整回放:replay_steps + diff_summary。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    plan_ref: str
    replay_steps: tuple[ReplayStep, ...]
    diff_summary: ReplayDiffSummary
    replayed_at: str


__all__ = [
    "ReplayDiffSummary",
    "ReplayStep",
    "RunReplay",
]
