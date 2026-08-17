"""Required session event vocabulary (spec §2.2.3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.harness.session import session_event
from lca.contracts.harness.skill import SkillCatalogEntry


@session_event("session.created.v1", visibility="audit")
@dataclass(frozen=True)
class SessionCreated:
    profile: str
    preset: str | None = None


@session_event("message.accepted.v1")
@dataclass(frozen=True)
class MessageAccepted:
    message_id: str
    role: str
    content_ref: str


@session_event("attachment.committed.v1", visibility="audit")
@dataclass(frozen=True)
class AttachmentCommitted:
    attachment_id: str
    name: str
    size_bytes: int
    mime_type: str


@session_event("command.rejected.v1", visibility="audit")
@dataclass(frozen=True)
class CommandRejected:
    command_type: str
    reason: str


@session_event("turn.started.v1")
@dataclass(frozen=True)
class TurnStarted:
    turn: int


@session_event("turn.ended.v1")
@dataclass(frozen=True)
class TurnEnded:
    turn: int
    reason: str


@session_event("step.started.v1")
@dataclass(frozen=True)
class StepStarted:
    turn: int
    step: int


@session_event("step.ended.v1")
@dataclass(frozen=True)
class StepEnded:
    turn: int
    step: int


@session_event("context.injected.v1", visibility="audit")
@dataclass(frozen=True)
class ContextInjected:
    source: str
    content_ref: str
    model_visible: bool = True


@session_event("skill.catalog.published.v1", visibility="audit")
@dataclass(frozen=True)
class SkillCatalogPublished:
    entries: tuple[SkillCatalogEntry, ...]
    digest: str
    source: str = "pre_step"


@session_event("skill.loaded.v1", visibility="audit")
@dataclass(frozen=True)
class SkillLoaded:
    skill_id: str
    content_hash: str
    invocation: str


@session_event("skill.user_invoked.v1", visibility="audit")
@dataclass(frozen=True)
class SkillUserInvoked:
    skill_id: str
    raw_text: str


@session_event("model.requested.v1", visibility="audit")
@dataclass(frozen=True)
class ModelRequested:
    turn: int
    step: int
    provider: str
    model: str


@session_event("model.completed.v1", visibility="audit")
@dataclass(frozen=True)
class ModelCompleted:
    turn: int
    step: int
    usage: dict | None = None


@session_event("model.failed.v1", visibility="audit")
@dataclass(frozen=True)
class ModelFailed:
    turn: int
    step: int
    error: str


@session_event("tool.called.v1")
@dataclass(frozen=True)
class ToolCalled:
    call_id: str
    tool_name: str
    arguments_ref: str
    provider_id: str | None = None


@session_event("tool.completed.v1")
@dataclass(frozen=True)
class ToolCompleted:
    call_id: str
    success: bool
    result_ref: str
    error: str | None = None


@session_event("tool.approval_requested.v1")
@dataclass(frozen=True)
class ToolApprovalRequested:
    call_id: str
    approval_type: str
    description: str


@session_event("tool.approval_resolved.v1")
@dataclass(frozen=True)
class ToolApprovalResolved:
    call_id: str
    decision: str


@session_event("inbox.spliced.v1")
@dataclass(frozen=True)
class InboxSpliced:
    op: str
    target: str
    message_ids: tuple[str, ...]


@session_event("assistant.responded.v1")
@dataclass(frozen=True)
class AssistantResponded:
    """Assistant text response — surface event for derive_messages().

    Aligned with DSH ``assistant/message`` surface event.
    """

    turn: int
    step: int
    content: str
    tool_calls: list[dict[str, Any]] | None = None


@session_event("session.checkpoint.v1", visibility="internal")
@dataclass(frozen=True)
class SessionCheckpoint:
    status: str
    snapshot_ref: str | None = None
    answer: str | None = None
    error: str | None = None
