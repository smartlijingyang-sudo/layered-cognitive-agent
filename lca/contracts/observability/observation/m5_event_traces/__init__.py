"""M5 — Event traces (决策 / 控制 / 工具 / LLM / reducer).

Producers: observation.decision_trace, observation.control_trace,
          observation.tool_call_trace, observation.llm_call_trace,
          observation.runtime_bookkeeping
Consumers: lca-ops trace show --filter kind=..., diagnosis.failure_explainer
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class DecisionTrace(BaseModel):
    """决策产生 / 拒绝。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    decision_id: str
    source_node_id: str
    action_type: str | None = None
    payload: dict[str, Any] = {}
    candidates: tuple[dict[str, Any], ...] = ()
    chosen_index: int | None = None
    rationale: str | None = None
    accepted: bool
    occurred_at: str


class ControlTrace(BaseModel):
    """控制面事件:allow / deny / stop。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    source_node_id: str
    control_slot: str  # observe / authorize / budget / constrain / ...
    verdict: str  # allow / deny / stop
    reason: str | None = None
    contract_clause: str | None = None
    observed_value: dict[str, Any] | None = None
    occurred_at: str


class ToolCallTrace(BaseModel):
    """tool 调用 + 结果。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    source_node_id: str
    tool_name: str
    args: dict[str, Any]
    result: dict[str, Any] | None = None
    success: bool
    elapsed_ms: int = 0
    retry_count: int = 0
    occurred_at: str


class LLMCallTrace(BaseModel):
    """LLM 请求 + 响应。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    source_node_id: str
    model: str
    prompt_digest: str
    response_digest: str
    token_usage: dict[str, int] = {}
    latency_ms: int = 0
    cache_hit: bool = False
    success: bool = True
    occurred_at: str


class ReducerApply(BaseModel):
    """reducer apply_* 事件,默认 verbose。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    method: str  # apply_step_advanced / apply_perception / apply_error / ...
    outcome: str  # success / error / failure
    args_digest: str | None = None
    state_diff_digest: str | None = None
    exception_class: str | None = None
    phase_boundary: bool = False
    elapsed_ms: int = 0
    occurred_at: str


__all__ = [
    "ControlTrace",
    "DecisionTrace",
    "LLMCallTrace",
    "ReducerApply",
    "ToolCallTrace",
]
