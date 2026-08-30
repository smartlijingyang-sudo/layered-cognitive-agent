"""journal 事件词表登记簿 —— ADR-0063 PR-7 source inversion 后的最小入口。

历史双表 ``JOURNAL_CATALOG`` + ``JOURNAL_CATALOG_META`` 已并入
``EventDescriptorRegistry``（``lca.layer0_infra.observability.event_descriptors_data.build_default_registry``）。

本模块仅保留：
- ``JOURNAL_EVENT_CLASSES``：class registry（事件名 → payload 类）。
  仍是反序列化与 ``RunStore.append`` fail-fast 校验的单一源。
- ``JournalSchemaMeta``：保留 dataclass 形状供迁移期引用；构造
  ``EventDescriptor`` 时由 ``event_descriptors_data._descriptor`` 调用，
  新代码不应再直接 import ``JournalSchemaMeta``。

新增事件 = journal.py 一个 frozen dataclass + ``event_descriptors_data.py``
一行 ``_descriptor(...)`` + ``build_default_registry()`` 末尾追加；
CI 守卫由 ``tests/test_observability_boundary.py`` 覆盖。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from lca.contracts.models.observability.journal import (
    ActionDegraded,
    AgentRunFinished,
    AgentRunStarted,
    ApprovalRequested,
    ApprovalResolved,
    AttachmentStagingCompleted,
    AttachmentStagingFailed,
    AttachmentStagingStarted,
    CastingCompleted,
    CastingFailed,
    CastingStarted,
    ContextCompacted,
    ContextManifested,
    DecisionMade,
    DelegationCacheHit,
    DelegationCompleted,
    DelegationIssued,
    GateDecided,
    InboxFollowupCreated,
    JournalEvent,
    LlmCallCompleted,
    LlmCallStarted,
    MemoryCommitted,
    PerceptionMerged,
    PluginAuthored,
    PluginInspected,
    PluginMounted,
    PluginMountRejected,
    PluginUnmounted,
    PresetPublished,
    ReasoningCompleted,
    ReasoningDelta,
    RunActivity,
    RunPaused,
    RunResumed,
    RuntimeObserved,
    SandboxOutputDelta,
    StepCompleted,
    StepTextDelta,
    SynthesisCompleted,
    TaskCreated,
    TeamMessagePublished,
    TeamRunFinished,
    TeamRunStarted,
    ToolCallStreaming,
    ToolDenied,
    ToolInvoked,
    ToolStarted,
)

# ── 词表登记（class registry） ───────────────────────────

JOURNAL_EVENT_CLASSES: dict[str, type[JournalEvent]] = {
    cls.__name__: cls
    for cls in (
        CastingStarted,
        CastingCompleted,
        CastingFailed,
        TeamRunStarted,
        TeamRunFinished,
        TaskCreated,
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
        RuntimeObserved,
        ContextManifested,
        PerceptionMerged,
        GateDecided,
        InboxFollowupCreated,
        TeamMessagePublished,
        ApprovalRequested,
        ApprovalResolved,
        MemoryCommitted,
        ContextCompacted,
        RunPaused,
        RunResumed,
        PluginAuthored,
        PluginMounted,
        PluginMountRejected,
        PluginUnmounted,
        PluginInspected,
        PresetPublished,
    )
}


# ── 兼容：JournalSchemaMeta dataclass 保留以备迁移期类型注解 ──


@dataclass(frozen=True)
class JournalSchemaMeta:
    """Schema 级元数据（ADR-0055 N6）；迁移期保留，构造 EventDescriptor 由
    ``event_descriptors_data`` 内部使用。新代码应直接读 ``EventDescriptor``。"""

    durability: Literal["required", "best_effort"]
    audience: Literal["end_user", "operator", "auditor", "restricted"]
    sensitivity: Literal["public", "internal", "confidential"]
    retention_class: str = "default"


__all__ = ["JOURNAL_EVENT_CLASSES", "JournalSchemaMeta"]
