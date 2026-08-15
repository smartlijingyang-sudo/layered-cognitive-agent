"""journal 事件词表登记簿 —— JOURNAL_EVENT_CLASSES / JOURNAL_CATALOG / JOURNAL_CATALOG_META。

词表治理（ADR-0037）+ 数据分类声明（ADR-0055 N6）。

与 ``telemetry_catalog.py`` 同构：每个 journal 事件类登记域（domain）/
唯一发射模块（emitter）/ 必备字段。守卫测试强制「一事件一发射点」；
新增事件 = journal.py 一个 dataclass + 本文件一行登记 + 一行分类，缺一即 CI 失败。

``JournalSchemaMeta`` 是 schema 级声明——所有该类型的实例共享同一份元数据，
决定投递保证（durability）、受众过滤（audience）、敏感等级和保留策略。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from lca.contracts.models.observability.journal import (
    ActionDegraded,
    AgentRunFinished,
    AgentRunStarted,
    AttachmentStagingCompleted,
    AttachmentStagingFailed,
    AttachmentStagingStarted,
    CastingCompleted,
    CastingFailed,
    CastingStarted,
    DecisionMade,
    DelegationCacheHit,
    DelegationCompleted,
    DelegationIssued,
    JournalEvent,
    LlmCallCompleted,
    LlmCallStarted,
    ReasoningCompleted,
    ReasoningDelta,
    RunActivity,
    RunInsight,
    SandboxOutputDelta,
    StepCompleted,
    StepTextDelta,
    SynthesisCompleted,
    TeamRunFinished,
    TeamRunStarted,
    ToolCallStreaming,
    ToolDenied,
    ToolInvoked,
    ToolStarted,
)
from lca.contracts.models.observability.telemetry_catalog import VocabDef, VocabDomain, VocabKind

# ── 词表登记 ────────────────────────────────────────────

JOURNAL_EVENT_CLASSES: dict[str, type[JournalEvent]] = {
    cls.__name__: cls
    for cls in (
        CastingStarted,
        CastingCompleted,
        CastingFailed,
        TeamRunStarted,
        TeamRunFinished,
        AgentRunStarted,
        AgentRunFinished,
        DelegationIssued,
        DelegationCompleted,
        DelegationCacheHit,
        SynthesisCompleted,
        DecisionMade,
        StepCompleted,
        ActionDegraded,
        LlmCallCompleted,
        LlmCallStarted,
        StepTextDelta,
        ReasoningDelta,
        ReasoningCompleted,
        RunActivity,
        SandboxOutputDelta,
        ToolCallStreaming,
        ToolStarted,
        ToolInvoked,
        ToolDenied,
        AttachmentStagingStarted,
        AttachmentStagingCompleted,
        AttachmentStagingFailed,
        RunInsight,
    )
}


# ── 数据分类声明（ADR-0055 N6）──────────────────────────


@dataclass(frozen=True)
class JournalSchemaMeta:
    """Schema 级元数据：所有该类型的实例共享同一份分类声明。

    - ``durability``：required = 不可静默丢失；best_effort = 高压时可丢。
    - ``audience``：end_user = SSE live 可见；operator = 运维可见；
      auditor = 审计可见；restricted = 不进 SSE live 帧。
    - ``sensitivity``：public / internal / confidential。
    - ``retention_class``：保留策略标识（default / short / permanent）。
    """

    durability: Literal["required", "best_effort"]
    audience: Literal["end_user", "operator", "auditor", "restricted"]
    sensitivity: Literal["public", "internal", "confidential"]
    retention_class: str = "default"


JOURNAL_CATALOG_META: dict[str, JournalSchemaMeta] = {
    # 容器事件
    "TeamRunStarted": JournalSchemaMeta("required", "auditor", "internal"),
    "TeamRunFinished": JournalSchemaMeta("required", "auditor", "internal"),
    "AgentRunStarted": JournalSchemaMeta("required", "auditor", "internal"),
    "AgentRunFinished": JournalSchemaMeta("required", "auditor", "internal"),
    # 选角
    "CastingStarted": JournalSchemaMeta("best_effort", "operator", "internal"),
    "CastingCompleted": JournalSchemaMeta("required", "auditor", "internal"),
    "CastingFailed": JournalSchemaMeta("required", "auditor", "internal"),
    # 协作
    "DelegationIssued": JournalSchemaMeta("required", "auditor", "internal"),
    "DelegationCompleted": JournalSchemaMeta("required", "auditor", "internal"),
    "DelegationCacheHit": JournalSchemaMeta("best_effort", "operator", "internal"),
    "SynthesisCompleted": JournalSchemaMeta("required", "operator", "internal"),
    # 认知事实
    "DecisionMade": JournalSchemaMeta("required", "operator", "internal"),
    "StepCompleted": JournalSchemaMeta("best_effort", "operator", "internal"),
    "ActionDegraded": JournalSchemaMeta("required", "operator", "internal"),
    # 资源事实（高压增量 — best_effort）
    "StepTextDelta": JournalSchemaMeta("best_effort", "end_user", "public", "short"),
    "ReasoningDelta": JournalSchemaMeta("best_effort", "restricted", "confidential", "short"),
    "ReasoningCompleted": JournalSchemaMeta("best_effort", "restricted", "confidential", "short"),
    "RunActivity": JournalSchemaMeta("best_effort", "end_user", "public", "short"),
    "SandboxOutputDelta": JournalSchemaMeta("best_effort", "end_user", "public", "short"),
    "LlmCallStarted": JournalSchemaMeta("best_effort", "operator", "internal", "short"),
    # 资源事实（关键 — required）
    "LlmCallCompleted": JournalSchemaMeta("required", "operator", "internal"),
    "ToolCallStreaming": JournalSchemaMeta("best_effort", "end_user", "public", "short"),
    "ToolStarted": JournalSchemaMeta("required", "operator", "internal"),
    "ToolInvoked": JournalSchemaMeta("required", "operator", "internal"),
    "ToolDenied": JournalSchemaMeta("required", "auditor", "internal"),
    # 附件暂存
    "AttachmentStagingStarted": JournalSchemaMeta("best_effort", "operator", "internal"),
    "AttachmentStagingCompleted": JournalSchemaMeta("best_effort", "operator", "internal"),
    "AttachmentStagingFailed": JournalSchemaMeta("required", "operator", "internal"),
    # 洞察
    "RunInsight": JournalSchemaMeta("best_effort", "operator", "internal"),
}


def _journal(
    domain: VocabDomain, emitter: str, *, required: tuple[str, ...] = (), desc: str
) -> VocabDef:
    return VocabDef(domain, VocabKind.EVENT, emitter, required, desc)


JOURNAL_CATALOG: dict[str, VocabDef] = {
    "CastingStarted": _journal(
        VocabDomain.TEAM,
        "gateway.assemble",
        required=("objective_preview",),
        desc="自动组队选角开始",
    ),
    "CastingCompleted": _journal(
        VocabDomain.TEAM,
        "gateway.assemble",
        required=("governance_kind",),
        desc="自动组队选角完成",
    ),
    "CastingFailed": _journal(
        VocabDomain.TEAM,
        "gateway.assemble",
        required=("error",),
        desc="自动组队选角失败",
    ),
    "TeamRunStarted": _journal(
        VocabDomain.RUN, "lca.layer3_agent.team_handle", desc="团队 run 开启（场景卡）"
    ),
    "TeamRunFinished": _journal(
        VocabDomain.RUN,
        "lca.layer3_agent.team_handle",
        required=("status",),
        desc="团队 run 关闭",
    ),
    "AgentRunStarted": _journal(
        VocabDomain.RUN,
        "lca.layer3_agent.cognitive_agent",
        required=("agent_role",),
        desc="agent run 开启",
    ),
    "AgentRunFinished": _journal(
        VocabDomain.RUN,
        "lca.layer3_agent.cognitive_agent",
        required=("status",),
        desc="agent run 关闭",
    ),
    "DelegationIssued": _journal(
        VocabDomain.TEAM,
        "lca.layer0_infra.transport.invocation",
        required=("delegation_id", "callee_role"),
        desc="委派发起（一等公民）",
    ),
    "DelegationCompleted": _journal(
        VocabDomain.TEAM,
        "lca.layer0_infra.transport.invocation",
        required=("delegation_id",),
        desc="委派回执",
    ),
    "DelegationCacheHit": _journal(
        VocabDomain.TEAM,
        "lca.layer1_cognitive.body.delegation_cache",
        required=("callee_role",),
        desc="委派幂等短路",
    ),
    "SynthesisCompleted": _journal(
        VocabDomain.TEAM,
        "lca.layer1_cognitive.body.action_handlers",
        desc="收口综合完成",
    ),
    "DecisionMade": _journal(
        VocabDomain.EVENT,
        "lca.layer1_cognitive.body.action_handlers",
        required=("action_type",),
        desc="决策事实",
    ),
    "StepCompleted": _journal(
        VocabDomain.EVENT, "lca.layer4_app.telemetry_bridge", required=("step",), desc="步完成"
    ),
    "ActionDegraded": _journal(
        VocabDomain.EVENT, "lca.layer4_app.telemetry_bridge", desc="动作降级"
    ),
    "LlmCallCompleted": _journal(
        VocabDomain.RESOURCE,
        "lca.layer0_infra.observability.adapters",
        required=("model",),
        desc="LLM 调用完成",
    ),
    "LlmCallStarted": _journal(
        VocabDomain.RESOURCE,
        "lca.layer0_infra.observability.adapters",
        required=("step",),
        desc="LLM 调用开始",
    ),
    "RunActivity": _journal(
        VocabDomain.RESOURCE,
        "lca.layer0_infra.observability",
        required=("phase",),
        desc="Run 级活动心跳",
    ),
    "StepTextDelta": _journal(
        VocabDomain.RESOURCE,
        "lca.layer0_infra.observability.adapters",
        required=("step", "seq"),
        desc="认知步 LLM 增量文本（中性）",
    ),
    "ReasoningDelta": _journal(
        VocabDomain.RESOURCE,
        "lca.layer0_infra.observability.adapters",
        required=("step", "seq"),
        desc="模型思维链增量",
    ),
    "ReasoningCompleted": _journal(
        VocabDomain.RESOURCE,
        "lca.layer0_infra.observability.adapters",
        required=("step",),
        desc="模型思维链段结束",
    ),
    "SandboxOutputDelta": _journal(
        VocabDomain.RESOURCE,
        "lca.layer0_infra.sandbox",
        required=("invocation_id", "stream", "seq"),
        desc="沙箱执行增量输出（stdout/stderr）",
    ),
    "ToolCallStreaming": _journal(
        VocabDomain.RESOURCE,
        "lca.layer1_cognitive.brain.llm_turn.executor",
        required=("tool_name",),
        desc="LLM 正在流式生成工具调用参数（早期卡片占位，消除思考→执行空白期）",
    ),
    "ToolStarted": _journal(
        VocabDomain.RESOURCE,
        "lca.layer1_cognitive.body.safe_executor",
        required=("tool_name", "invocation_id"),
        desc="工具调用开始；plugin_state 为 UI 完整初始态（code/command）",
    ),
    "ToolInvoked": _journal(
        VocabDomain.RESOURCE,
        "lca.layer1_cognitive.body.safe_executor",
        required=("tool_name",),
        desc="工具调用完成；plugin_state/files 为 UI 一等字段（不截断）",
    ),
    "ToolDenied": _journal(
        VocabDomain.RESOURCE,
        "lca.layer1_cognitive.body.safe_executor",
        required=("tool_name",),
        desc="工具调用被拒",
    ),
    "AttachmentStagingStarted": _journal(
        VocabDomain.RESOURCE,
        "gateway.runs.execute",
        required=("plane_id", "file_count"),
        desc="附件暂存开始（host → machine bootstrap channel）",
    ),
    "AttachmentStagingCompleted": _journal(
        VocabDomain.RESOURCE,
        "gateway.runs.execute",
        required=("plane_id", "file_count"),
        desc="附件暂存完成",
    ),
    "AttachmentStagingFailed": _journal(
        VocabDomain.RESOURCE,
        "gateway.runs.execute",
        required=("plane_id", "error"),
        desc="附件暂存失败（路径拒绝、传输超时、IO 错误）",
    ),
    "RunInsight": _journal(
        VocabDomain.EVENT,
        "lca.layer0_infra.observability.journal.insight",
        required=("kind",),
        desc="计算洞察",
    ),
}
