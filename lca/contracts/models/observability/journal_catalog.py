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
    DecisionMade,
    DelegationCacheHit,
    DelegationCompleted,
    DelegationIssued,
    JournalEvent,
    LlmCallCompleted,
    RunInsight,
    StepCompleted,
    StepTextDelta,
    SynthesisCompleted,
    TeamRunFinished,
    TeamRunStarted,
    ToolDenied,
    ToolInvoked,
)
from lca.contracts.models.observability.telemetry_catalog import VocabDef, VocabDomain, VocabKind

# ── 词表登记 ────────────────────────────────────────────

JOURNAL_EVENT_CLASSES: dict[str, type[JournalEvent]] = {
    cls.__name__: cls
    for cls in (
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
        StepTextDelta,
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
    "StepTextDelta": _journal(
        VocabDomain.RESOURCE,
        "lca.layer0_infra.observability.adapters",
        required=("step", "seq"),
        desc="认知步 LLM 增量文本（中性）",
    ),
    "ToolInvoked": _journal(
        VocabDomain.RESOURCE,
        "lca.layer1_cognitive.body.safe_executor",
        required=("tool_name",),
        desc="工具调用完成",
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
