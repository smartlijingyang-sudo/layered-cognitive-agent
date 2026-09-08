"""Required session event vocabulary (spec §2.2.3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

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

    ``effect_kind`` classifies the activation receipt as
    ``"stateful_once"`` per ADR-0203 — repeated activations within the
    same run are semantic no-ops (the second call returns the prior
    receipt rather than re-emitting the side effect). The field defaults
    to ``"stateful_once"`` so historical callers without an explicit
    classification still classify correctly.
    """

    skill_id: str
    name: str
    content_hash: str = ""
    activated_at_step: int = 0
    source: str = "tool"
    effect_kind: Literal["stateful_once"] = "stateful_once"


@session_event("skill.routed.v1", visibility="audit")
@dataclass(frozen=True)
class SkillRouted:
    """One prompt-template routing decision produced by a SkillRouter."""

    template_id: str
    decision_path: str
    source: str = "skill_router"


@session_event("skill.searched.v1", visibility="audit")
@dataclass(frozen=True)
class SkillSearched:
    """Operational skill search audit (``search_skill`` tool)."""

    query: str
    result_count: int
    source: str = "tool:search_skill"
    page: int = 1
    page_size: int = 20


@session_event("tool.schema.published.v1", visibility="audit")
@dataclass(frozen=True)
class ToolSchemaPublished:
    """Run-resolved tool manifest digest (factory materialize boundary)."""

    tool_names: tuple[str, ...]
    digest: str


@session_event("prompt.section.published.v1", visibility="audit")
@dataclass(frozen=True)
class PromptSectionPublished:
    """One prompt section rendered into the model request (digest-only audit)."""

    section_key: str
    digest: str
    template_id: str = ""
    text_chars: int = 0


@session_event("assistant.run.bound.v1", visibility="audit")
@dataclass(frozen=True)
class AssistantRunBound:
    """Run bound to an assistant Home (ADR-0187 §3 D7)."""

    assistant_id: str
    run_id: str
    profile: str = ""


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


@session_event("gate.decided.v1", visibility="model")
@dataclass(frozen=True)
class GateDecidedCommitted:
    """Durable gate verdict for Session SSOT fold (ADR-0191 R1)."""

    event_id: str
    gate: str
    verdict: str
    is_rewritten: bool
    step: int
    policy_fact_kind: str = ""
    policy_fact_message: str = ""
    policy_fact_source: str = ""
    tool_name: str | None = None
    rationale: str | None = None


@session_event("context.manifested.v1", visibility="model")
@dataclass(frozen=True)
class ContextManifestCommitted:
    """Durable ContextManifest snapshot for Session SSOT fold (ADR-0191 R1)."""

    step: int
    digest: str
    items: tuple[dict[str, Any], ...] = ()


@session_event("delivery.evidence.v1", visibility="audit")
@dataclass(frozen=True)
class DeliveryEvidenceCommitted:
    """Folded delivery evidence snapshot for convergence debug (ADR-0196)."""

    step: int
    task_class: str
    artifact_count: int
    producer_success_count: int
    satisfied: bool
    detail: str = ""


@session_event("convergence.evaluated.v1", visibility="audit")
@dataclass(frozen=True)
class ConvergenceEvaluatedCommitted:
    """Convergence policy verdict for debug-run (ADR-0196)."""

    step: int
    kind: str
    rationale: str
    task_class: str
    satisfied: bool
    detail: str = ""


@session_event("prompt.surface.rendered.v1", visibility="audit")
@dataclass(frozen=True)
class PromptSurfaceRenderedCommitted:
    """PromptSurface render audit — tools/sandbox SSOT (ADR-0196)."""

    step: int
    task_class: str
    tool_count: int
    include_full_sandbox: bool
    digest: str


@session_event("tool.denied.v1", visibility="model")
@dataclass(frozen=True)
class ToolDeniedCommitted:
    """Durable tool denial for Session SSOT (ADR-0194 P1-10; maps to ``ToolDenied``)."""

    tool_name: str
    reason: str


@session_event("tool.call.resolved.v1", visibility="model")
@dataclass(frozen=True)
class ToolCallResolvedCommitted:
    """Durable LLM tool-call args resolution for Session SSOT (ADR-0194 P1-12).

    Maps to ``ToolCallResolved`` journal event; emitted when streaming args complete.
    """

    tool_name: str
    tool_call_id: str
    arguments: dict[str, Any] = field(default_factory=dict)
    arguments_ref: dict[str, Any] | None = None


@session_event("tool.started.v1", visibility="model")
@dataclass(frozen=True)
class ToolStartedCommitted:
    """Durable tool call start for Session SSOT (ADR-0194 P1-10; maps to ``ToolStarted``)."""

    tool_name: str
    invocation_id: str
    arguments: dict[str, Any] = field(default_factory=dict)
    arguments_ref: dict[str, Any] | None = None
    idempotency_key: str = ""


@session_event("tool.invoked.v1", visibility="model")
@dataclass(frozen=True)
class ToolInvokedCommitted:
    """Durable tool call completion for Session SSOT (ADR-0194 P1-10; maps to ``ToolInvoked``)."""

    tool_name: str
    invocation_id: str
    ok: bool = True
    latency_ms: int = 0
    attempt: int = 1
    error: str = ""
    idempotency_key: str = ""
    files: tuple[dict[str, Any], ...] = ()
    arguments: dict[str, Any] = field(default_factory=dict)
    arguments_ref: dict[str, Any] | None = None
    output_ref: dict[str, Any] | None = None
    output_text: str | None = None
    output_truncated: bool = False
    projected_state: dict[str, Any] = field(default_factory=dict)


@session_event("decision.made.v1", visibility="model")
@dataclass(frozen=True)
class DecisionMadeCommitted:
    """Durable decision fact for Session SSOT (ADR-0194 P1-11; maps to ``DecisionMade``)."""

    step: int = 0
    action_type: str = ""
    rationale_preview: str = ""
    delegate_target: str = ""
    delegate_count: int = 0
    tool_name: str = ""
    confidence: float = 0.0
    response_text: str = ""
    output_truncated: bool = False


@session_event("approval.requested.v1", visibility="model")
@dataclass(frozen=True)
class ApprovalRequestedCommitted:
    """Durable HIL approval queue fact (ADR-0194 P1-11; maps to ``ApprovalRequested``)."""

    envelope_id: str = ""
    tool_name: str = ""
    capability_grant: str = ""
    risk_level: str = ""


@session_event("synthesis.completed.v1", visibility="model")
@dataclass(frozen=True)
class SynthesisCompletedCommitted:
    """Board synthesis completion for Session SSOT (maps to ``SynthesisCompleted``)."""

    method: str = ""
    candidate_count: int = 0
    output_text: str = ""
    output_truncated: bool = False


@session_event("team.message.published.v1", visibility="model")
@dataclass(frozen=True)
class TeamMessagePublishedCommitted:
    """Team inbox message for Session SSOT (maps to ``TeamMessagePublished``)."""

    team_id: str = ""
    thread_id: str = ""
    sender_role: str = ""
    recipient_role: str = ""
    step: int = 0
    body_preview: str = ""


@session_event("memory.committed.v1", visibility="model")
@dataclass(frozen=True)
class MemoryCommittedCommitted:
    """Memory layer write for Session SSOT (ADR-0194 P1-13; maps to ``MemoryCommitted``)."""

    layer: str = ""
    record_kind: str = ""
    record_id: str = ""


@session_event("context.compacted.v1", visibility="model")
@dataclass(frozen=True)
class ContextCompactedCommitted:
    """Compaction audit for Session SSOT (ADR-0194 P1-13; maps to ``ContextCompacted``)."""

    step: int = 0
    original_kinds: tuple[str, ...] = ()
    kept_kinds: tuple[str, ...] = ()
    mode: str = "selection"
    applied: bool = False
    reason: str = ""
    source_record_count: int = 0
    summary_record_id: str = ""
    original_characters: int = 0
    result_characters: int = 0
    compression_ratio: float = 0.0
    coverage_ratio: float = 0.0


@session_event("turn.control.v1", visibility="internal")
@dataclass(frozen=True)
class TurnControlCommitted:
    """Control-plane turn summary for gate/projection fold (ADR-0191 Wave C)."""

    action_type: str
    tool_name: str | None = None
    observation_success: bool | None = None
    tool_arguments: dict[str, Any] | None = None
    observation_payload: Any | None = None
    observation_error: str | None = None
    files_created: tuple[str, ...] = ()


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
