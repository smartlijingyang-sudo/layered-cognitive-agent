"""journal 事件 → span/event 属性映射（纯函数层，无 OTel 依赖）。

投影的"数据变换"与"span 状态机"分离：本模块只做 event → attributes dict
的纯映射（可脱离 OTel 单测），``otel_projector`` 负责 span 生命周期与父子
解析。Langfuse 约定（observation.type / session.id / tags / gen_ai）在此
单点盖章。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lca.contracts.atoms.telemetry import (
    ATTR_ACTION_TYPE,
    ATTR_AGENT_ROLE,
    ATTR_ATTEMPT,
    ATTR_CALLEE_ROLE,
    ATTR_CALLER_ROLE,
    ATTR_CANDIDATE_COUNT,
    ATTR_CONFIDENCE,
    ATTR_DEGRADED_TO,
    ATTR_DELEGATE_COUNT,
    ATTR_DELEGATE_TARGET,
    ATTR_ERROR,
    ATTR_FROM_ROLE,
    ATTR_LATENCY_MS,
    ATTR_LEAD_ROLE,
    ATTR_MANDATE,
    ATTR_MECHANISM,
    ATTR_MEMBERS,
    ATTR_OBJECTIVE,
    ATTR_OBJECTIVE_PREVIEW,
    ATTR_OK,
    ATTR_ORIGINAL_ACTION_TYPE,
    ATTR_PARALLEL_GROUP,
    ATTR_PLAN_STEPS,
    ATTR_RATIONALE_PREVIEW,
    ATTR_REASON,
    ATTR_RESULT_OUTPUT,
    ATTR_STATUS,
    ATTR_STEP,
    ATTR_STEPS,
    ATTR_STRATEGY_KEY,
    ATTR_SUBTASK_PREVIEW,
    ATTR_SYNTHESIS_METHOD,
    ATTR_TASK_ID,
    ATTR_TEAM_ID,
    ATTR_TOOL_NAME,
    EventName,
    SpanName,
)
from lca.contracts.models.observability.journal import (
    ActionDegraded,
    AgentRunFinished,
    AgentRunStarted,
    DecisionMade,
    DelegationCacheHit,
    DelegationCompleted,
    DelegationIssued,
    JournalEvent,
    StepCompleted,
    SynthesisCompleted,
    TeamRunFinished,
    TeamRunStarted,
    ToolDenied,
    ToolInvoked,
)
from lca.layer0_infra.observability.langfuse_conventions import (
    FRAMEWORK_TAG,
    LANGFUSE_OBSERVATION_INPUT,
    LANGFUSE_OBSERVATION_METADATA_AGENT_ROLE,
    LANGFUSE_OBSERVATION_OUTPUT,
    LANGFUSE_OBSERVATION_TYPE,
    LANGFUSE_TRACE_TAGS,
    OBSERVATION_TYPE_AGENT,
    OBSERVATION_TYPE_TOOL,
)

_LANGFUSE_SESSION_ID = "session.id"


def drop_empty(attributes: dict[str, Any]) -> dict[str, Any]:
    """去掉 None / 空串——span 属性只留有信息量的键。

    布尔（含 ``ok=False``）与数值（含 0）原样保留：失败与零值本身是事实。
    """
    return {key: value for key, value in attributes.items() if value is not None and value != ""}


def team_run_started_attrs(event: TeamRunStarted) -> dict[str, Any]:
    tags = [FRAMEWORK_TAG]
    if event.strategy_key:
        tags.append(event.strategy_key)
    return drop_empty(
        {
            ATTR_TEAM_ID: event.team_id,
            ATTR_STRATEGY_KEY: event.strategy_key,
            ATTR_MANDATE: event.mandate,
            ATTR_LEAD_ROLE: event.lead_role,
            ATTR_MEMBERS: ",".join(event.members),
            ATTR_OBJECTIVE_PREVIEW: event.objective_preview,
            ATTR_PLAN_STEPS: event.plan_steps,
            ATTR_OBJECTIVE: event.objective,
            _LANGFUSE_SESSION_ID: event.team_id,
            LANGFUSE_OBSERVATION_INPUT: event.objective,
            LANGFUSE_TRACE_TAGS: tags,
        }
    )


def team_run_finished_attrs(event: TeamRunFinished) -> dict[str, Any]:
    return drop_empty(
        {
            ATTR_STATUS: event.status,
            ATTR_STEPS: event.steps,
            ATTR_ERROR: event.error,
            ATTR_RESULT_OUTPUT: event.output_text,
            LANGFUSE_OBSERVATION_OUTPUT: event.output_text,
        }
    )


def agent_run_started_attrs(event: AgentRunStarted) -> dict[str, Any]:
    return drop_empty(
        {
            ATTR_AGENT_ROLE: event.agent_role,
            ATTR_STRATEGY_KEY: event.strategy_key,
            ATTR_FROM_ROLE: event.from_role,
            ATTR_OBJECTIVE_PREVIEW: event.objective_preview,
            ATTR_OBJECTIVE: event.objective,
            LANGFUSE_OBSERVATION_TYPE: OBSERVATION_TYPE_AGENT,
            LANGFUSE_OBSERVATION_METADATA_AGENT_ROLE: event.agent_role,
            LANGFUSE_OBSERVATION_INPUT: event.objective,
        }
    )


def agent_run_finished_attrs(event: AgentRunFinished) -> dict[str, Any]:
    return drop_empty(
        {
            ATTR_STATUS: event.status,
            ATTR_STEPS: event.steps,
            ATTR_ERROR: event.error,
            ATTR_RESULT_OUTPUT: event.output_text,
            LANGFUSE_OBSERVATION_OUTPUT: event.output_text,
        }
    )


def delegation_issued_attrs(event: DelegationIssued) -> dict[str, Any]:
    mechanism = getattr(event.mechanism, "value", event.mechanism)
    return drop_empty(
        {
            ATTR_CALLER_ROLE: event.caller_role,
            ATTR_CALLEE_ROLE: event.callee_role,
            ATTR_SUBTASK_PREVIEW: event.subtask_preview,
            ATTR_MECHANISM: mechanism,
            ATTR_PARALLEL_GROUP: event.parallel_group,
        }
    )


def delegation_completed_attrs(event: DelegationCompleted) -> dict[str, Any]:
    return drop_empty(
        {
            ATTR_OK: event.ok,
            ATTR_STATUS: event.status,
            ATTR_TASK_ID: event.task_id,
            ATTR_RESULT_OUTPUT: event.output_text,
        }
    )


def tool_invoked_attrs(event: ToolInvoked) -> dict[str, Any]:
    return drop_empty(
        {
            ATTR_TOOL_NAME: event.tool_name,
            ATTR_OK: event.ok,
            ATTR_LATENCY_MS: event.latency_ms,
            ATTR_ATTEMPT: event.attempt,
            ATTR_ERROR: event.error,
            ATTR_RESULT_OUTPUT: event.result_preview,
            LANGFUSE_OBSERVATION_TYPE: OBSERVATION_TYPE_TOOL,
            LANGFUSE_OBSERVATION_INPUT: event.arguments_preview,
            LANGFUSE_OBSERVATION_OUTPUT: event.result_preview,
        }
    )


def decision_made_attrs(event: DecisionMade) -> dict[str, Any]:
    return drop_empty(
        {
            ATTR_STEP: event.step,
            ATTR_ACTION_TYPE: event.action_type,
            ATTR_RATIONALE_PREVIEW: event.rationale_preview,
            ATTR_DELEGATE_TARGET: event.delegate_target,
            ATTR_DELEGATE_COUNT: event.delegate_count,
            ATTR_TOOL_NAME: event.tool_name,
            ATTR_CONFIDENCE: event.confidence,
            ATTR_RESULT_OUTPUT: event.response_text,
            LANGFUSE_OBSERVATION_OUTPUT: event.response_text,
        }
    )


def step_completed_attrs(event: StepCompleted) -> dict[str, Any]:
    return drop_empty(
        {ATTR_STEP: event.step, ATTR_STATUS: event.status, ATTR_ACTION_TYPE: event.action_type}
    )


def action_degraded_attrs(event: ActionDegraded) -> dict[str, Any]:
    return drop_empty(
        {
            ATTR_ORIGINAL_ACTION_TYPE: event.original_action_type,
            ATTR_DEGRADED_TO: event.degraded_to,
            ATTR_STEP: event.step,
        }
    )


def tool_denied_attrs(event: ToolDenied) -> dict[str, Any]:
    return drop_empty({ATTR_TOOL_NAME: event.tool_name, ATTR_REASON: event.reason})


def delegation_cache_hit_attrs(event: DelegationCacheHit) -> dict[str, Any]:
    return drop_empty(
        {
            ATTR_CALLEE_ROLE: event.callee_role,
            ATTR_SUBTASK_PREVIEW: event.subtask_preview,
            ATTR_STEP: event.step,
        }
    )


def synthesis_completed_attrs(event: SynthesisCompleted) -> dict[str, Any]:
    return drop_empty(
        {
            ATTR_SYNTHESIS_METHOD: event.method,
            ATTR_CANDIDATE_COUNT: event.candidate_count,
            ATTR_RESULT_OUTPUT: event.output_text,
        }
    )


AttrMapper = Callable[[Any], dict[str, Any]]

#: 瞬时事实投影表：事件类型 → (OTel event 名, 属性映射)。
#: OtelProjector 据此统一落为所属 run span 的 event（非孤儿 0 秒 span）。
EVENT_PROJECTIONS: dict[type[JournalEvent], tuple[str, AttrMapper]] = {
    DecisionMade: (EventName.DECISION_MADE.value, decision_made_attrs),
    StepCompleted: (EventName.STEP_COMPLETED.value, step_completed_attrs),
    ActionDegraded: (EventName.ACTION_DEGRADED.value, action_degraded_attrs),
    ToolDenied: (EventName.TOOL_DENIED.value, tool_denied_attrs),
    DelegationCacheHit: (SpanName.DELEGATE_CACHE_HIT.value, delegation_cache_hit_attrs),
    SynthesisCompleted: (SpanName.TEAM_SYNTHESIS.value, synthesis_completed_attrs),
}
