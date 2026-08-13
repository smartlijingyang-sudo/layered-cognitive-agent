"""journal 事件词表登记簿 —— JOURNAL_EVENT_CLASSES / JOURNAL_CATALOG（ADR-0037）。

与 ``telemetry_catalog.py`` 同构：每个 journal 事件类登记域（domain）/
唯一发射模块（emitter）/ 必备字段。守卫测试强制「一事件一发射点」；
新增事件 = journal.py 一个 dataclass + 本文件一行登记，缺一即 CI 失败。
"""

from __future__ import annotations

from lca.contracts.models.observability.journal import (
    ActionDegraded,
    AgentRunFinished,
    AgentRunStarted,
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
        RunInsight,
    )
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
    "RunInsight": _journal(
        VocabDomain.EVENT,
        "lca.layer0_infra.observability.journal.insight",
        required=("kind",),
        desc="计算洞察",
    ),
}
