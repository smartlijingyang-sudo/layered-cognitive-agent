"""统一事件描述符查询层。

现有 Journal 类型注册、发射边界和分类表在本模块收束为 ``EventDescriptor``；
投影器和 Agent 诊断只依赖这一查询面，不得重新解释 audience、sensitivity 或
保留策略。
"""

from __future__ import annotations

from lca.contracts.models.observability.event import (
    EventAudience,
    EventDescriptor,
    EventDurability,
    EventPlane,
    EventSensitivity,
)
from lca.contracts.models.observability.journal import JournalEvent
from lca.contracts.models.observability.journal_catalog import (
    JOURNAL_CATALOG,
    JOURNAL_CATALOG_META,
)

_SURFACE = frozenset(
    {
        "StepTextDelta",
        "ReasoningDelta",
        "SandboxOutputDelta",
        "ToolCallStreaming",
        "ToolInvoked",
        "InboxFollowupCreated",
        "TeamMessagePublished",
        "ContextManifested",
    }
)
_STRUCTURAL = frozenset(
    {
        "TeamRunStarted",
        "TeamRunFinished",
        "AgentRunStarted",
        "AgentRunFinished",
        "DelegationIssued",
        "DelegationCompleted",
        "LlmCallStarted",
        "LlmCallCompleted",
        "ToolStarted",
        "ToolDenied",
        "StepCompleted",
        "RunPaused",
        "RunResumed",
    }
)


def _plane(type_name: str) -> EventPlane:
    if type_name == "RuntimeObserved":
        return EventPlane.EXPLANATION
    if type_name in _SURFACE:
        return EventPlane.SURFACE
    if type_name in _STRUCTURAL:
        return EventPlane.STRUCTURAL
    return EventPlane.STRUCTURAL


def _otel_kind(type_name: str) -> str:
    if type_name in {"AgentRunStarted", "AgentRunFinished", "TeamRunStarted", "TeamRunFinished"}:
        return "agent"
    if type_name == "LlmCallCompleted":
        return "generation"
    if type_name in {"ToolStarted", "ToolInvoked", "ToolDenied"}:
        return "tool"
    return "event"


EVENT_DESCRIPTORS: dict[str, EventDescriptor] = {
    type_name: EventDescriptor(
        type_name=type_name,
        plane=_plane(type_name),
        domain=str(definition.domain.value),
        emitter=definition.emitter,
        durability=EventDurability(meta.durability),
        audience=EventAudience(meta.audience),
        sensitivity=EventSensitivity(meta.sensitivity),
        retention=meta.retention_class,
        required=definition.required_attrs,
        description=definition.description,
        otel_kind=_otel_kind(type_name),  # type: ignore[arg-type]
    )
    for type_name, definition in JOURNAL_CATALOG.items()
    for meta in (JOURNAL_CATALOG_META[type_name],)
}


def descriptor_for(event: JournalEvent | str) -> EventDescriptor:
    """返回已登记事件的唯一治理描述符。"""
    type_name = event if isinstance(event, str) else type(event).__name__
    try:
        return EVENT_DESCRIPTORS[type_name]
    except KeyError as exc:
        raise KeyError(f"未登记的运行事件描述符：{type_name}") from exc


def may_export_externally(event: JournalEvent | str) -> bool:
    """外部 OTel/Langfuse 投影只接收非受限、非机密事件。"""
    descriptor = descriptor_for(event)
    return (
        descriptor.audience is not EventAudience.RESTRICTED
        and descriptor.sensitivity is not EventSensitivity.CONFIDENTIAL
    )


__all__ = ["EVENT_DESCRIPTORS", "descriptor_for", "may_export_externally"]
