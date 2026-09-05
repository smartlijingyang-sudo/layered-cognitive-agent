"""Required session event vocabulary (spec §2.2.3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.harness.memory.skill import SkillCatalogEntry
from lca.contracts.harness.tasks.session import session_event


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

    def __post_init__(self) -> None:
        if self.turn < 0 or self.step < 0:
            raise ValueError("step event coordinates must be non-negative")


@session_event("step.ended.v1")
@dataclass(frozen=True)
class StepEnded:
    turn: int
    step: int

    def __post_init__(self) -> None:
        if self.turn < 0 or self.step < 0:
            raise ValueError("step event coordinates must be non-negative")


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
    source: str = "perceive"


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


@session_event("skill.activated.v1", visibility="audit")
@dataclass(frozen=True)
class SkillActivated:
    """One skill whose instructions entered agent context as active guidance.

    ``source`` names the activation path, e.g. ``"tool:activate_skill"``,
    ``"slash:/skill"``, ``"skill_tool"``.
    """

    skill_id: str
    name: str
    content_hash: str = ""
    activated_at_step: int = 0
    source: str = "tool"


@session_event("skill.routed.v1", visibility="audit")
@dataclass(frozen=True)
class SkillRouted:
    """One prompt-template routing decision produced by a SkillRouter."""

    template_id: str
    decision_path: str
    source: str = "skill_router"


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


@session_event("thinking.delta.v1", visibility="audit")
@dataclass(frozen=True)
class ThinkingDelta:
    """One model reasoning increment mirrored into the Session log.

    Dual-write companion of journal ``ReasoningDelta``; ``seq`` is the
    per-step reasoning delta sequence, not the Session event seq.
    """

    turn: int
    step: int
    text_delta: str
    seq: int = 0


@session_event("thinking.completed.v1", visibility="audit")
@dataclass(frozen=True)
class ThinkingCompleted:
    """End of one model reasoning phase mirrored into the Session log.

    Dual-write companion of journal ``ReasoningCompleted``;
    ``content_preview`` carries the accumulated reasoning text.
    """

    turn: int
    step: int
    duration_ms: int
    content_preview: str


@session_event("approval.persisted.v1", visibility="internal")
@dataclass(frozen=True)
class ApprovalPersisted:
    """Durable declarative resume point for one approval-paused session."""

    approval_id: str
    resume_point: dict[str, object]


@session_event("approval.resolved.v1", visibility="internal")
@dataclass(frozen=True)
class ApprovalResolved:
    """One idempotent human decision over a persisted approval request."""

    approval_id: str
    command_id: str
    payload: str
    approved: bool = True


@session_event("inbox.spliced.v1")
@dataclass(frozen=True)
class InboxSpliced:
    op: str
    target: str
    message_ids: tuple[str, ...]
    # Appended messages are included so a pending queue can be rebuilt from the
    # existing append-only Session stream. Old events omit this optional field.
    messages: tuple[dict[str, str], ...] = ()


@session_event("assistant.responded.v1")
@dataclass(frozen=True)
class AssistantResponded:
    """Assistant text response — surface event for derive_messages()."""

    turn: int
    step: int
    content: str
    tool_calls: list[dict[str, Any]] | None = None


@session_event("session.title.v1", visibility="audit")
@dataclass(frozen=True)
class SessionTitle:
    """Latest-wins session title — log-only, never model-visible (ADR-0188).

    ``message_seqs`` are the session event seqs of the user messages used to
    derive this title (empty for an explicit user rename). ``source`` is one
    of ``"fallback"`` / ``"provider"`` / ``"user"``: the built-in
    deterministic fallback, a registered title provider, or an explicit user
    rename (which pins the title against automatic generation).
    """

    title: str
    message_seqs: tuple[int, ...]
    source: str


@session_event("session.checkpoint.v1", visibility="audit")
@dataclass(frozen=True)
class SessionCheckpoint:
    """生命周期恢复检查点——恢复面唯一权威(消费方见 ``plugins/session/runtime/recovery.py``)。

    ``status`` 取 :class:`LiveAgentStatus` 的 wire 值(``waiting_input`` /
    ``disposed`` / 历史终态 ``completed`` / ``failed`` / ``canceled``);
    ``working`` 禁止落检查点(恢复不变量)。
    """

    status: str


@session_event("session.end_seed.v1", visibility="audit")
@dataclass(frozen=True)
class SessionEndSeed:
    """Fork/restore 继承边界标记（DSH session/end-seed 对位）。"""


@session_event("feedback.record.v1", visibility="audit")
@dataclass(frozen=True)
class FeedbackRecord:
    """用户反馈记录 —— FEEDBACK_ONLY 遥测门控释放前缀（DSH feedback/record 对位）。"""

    rating: str | None = None
    tags: tuple[str, ...] = ()
    message_seqs: tuple[int, ...] = ()
    text: str | None = None
