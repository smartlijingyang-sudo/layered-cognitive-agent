"""Boundary typed DTOs (ADR-0220 §4).

Cross-graph transports between Layer 1 (primitive.*), Layer 2 (concept.*)
and Layer 3 (agent.*) graphs. Each DTO is closed under two contracts:
no surprise fields (``extra="forbid"``-equivalent) and no mutation
downstream (``frozen=True``-equivalent). The 7 boundary DTOs that already
existed as frozen dataclasses in their original modules (``Decision`` /
``EffectReceipt`` / ``Reflection`` / ``ReasonerTurnRender``) keep their
original location and got an audit pass adding explicit field rejection
semantics. The 4 NEW DTOs defined here (``BindingsView`` / ``ForkedTools``
/ ``RoleSnapshot`` / ``ReasonerBundle``) are pydantic ``BaseModel`` with
``model_config = ConfigDict(extra="forbid", frozen=True)``.

Three additional boundary DTOs (``TemplateSelection`` / ``MemoryReceipt``
/ ``StopPayload``) are also defined here per ADR-0220 §4.1 because they
have no pre-existing home and serve as cross-graph boundary types.
``ReasonerContext`` replaces the previous ``_ReasonerContextPlaceholder``
with the real typed fields (task / activated_skills / manifest).

Producers / consumers are tracked in ADR-0220 Appendix B.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.contracts.models.cognition.prompt_assembly import (
    PromptTemplateVariant,
    SelectorDecisionPath,
)
from lca.contracts.models.core.perceive.perception import ContextManifest
from lca.contracts.models.core.workspace.activation import ActivatedSkill
from lca.contracts.models.team.role.team import RoleProfile
from lca.contracts.models.team.team.awareness import TeamAwareness
from lca.contracts.protocols.runtime.infra.infra import Tool


class ReasonerContext(BaseModel):
    """Per-turn context bundle for ``concept.context.compose`` → ``concept.prompt.render``.

    Closed-set boundary: a ReasonerContext is whatever the perceive graph
    produced this turn (manifest), plus the active task string and the
    activated skill list. Downstream the prompt assembler never reads
    anything else from state — this is the contract that replaces the
    historical ``PromptReasoner`` duck-type reads.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)
    task: str
    activated_skills: tuple[ActivatedSkill, ...] = ()
    manifest: ContextManifest | None = None


class TemplateSelection(BaseModel):
    """Output of ``concept.template.select``.

    Carries the chosen ``template_id`` with the ``variant`` discriminator
    and the selector ``decision_path`` so downstream render nodes can
    record provenance without re-running the selector.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)
    template_id: str
    variant: PromptTemplateVariant
    decision_path: SelectorDecisionPath


class MemoryReceipt(BaseModel):
    """Output of ``concept.memory.write``.

    Reports whether the upstream ``Reflection`` was admitted into durable
    memory and the resulting reference (or rejection reason). Admit
    policy lives in the producer; this DTO is the read-only contract.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    admitted: bool
    memory_ref: str | None = None
    reflection_id: str = ""
    rejection_reason: str | None = None


class StopPayload(BaseModel):
    """Output of ``terminal.commit`` → ``apply_stop`` / ``apply_terminal_outcome``.

    Carries the loop's terminal payload. ``reason`` is set by the model
    (RESPOND with non-empty response_text maps to a focused payload),
    by ``act.observe.terminate_decide`` routing an unclassified
    host-side dispatch failure to ``terminal.commit`` (ERROR), or by the
    budget guard (BUDGET_EXCEEDED). ``final_output_ref`` is the optional
    pointer to the model's answer text; the reducer resolves it into
    ``TerminalOutcome.final_output``.

    The historical ``should_stop`` boolean and ``focus_converged`` flag
    are gone: loop termination is the terminal outcome itself, decided
    by the data shape (``reason`` and ``final_output_ref`` presence),
    not by a separate predicate.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    reason: str | None = None
    final_output_ref: str | None = None


class BindingsView(BaseModel):
    """Per-run bindings from RuntimePlane; replaces ``AgentState._xxx_ref``.

    ``mode`` carries the run-coordination mode selected for this turn
    (``"solo"`` / ``"cordis-creator"`` / ``"team"``). It is the typed
    signal tool-visibility gates must read — sandbox plane ≠ creator
    mode (sandbox is isolation, mode is policy). See
    ``lca.nodes.concept.tool_fork.dispatch`` for the consumer.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)
    file_store: object | None = None
    sandbox: object | None = None
    skill_store: object | None = None
    machine_resolver: object | None = None
    search: object | None = None
    bindings: object | None = None
    mode: str = "solo"
    assistant_id: str = ""
    """ADR-0242 D4: non-empty ⇒ tool fork must narrow to Home policy."""
    home_path: str | None = None
    """Assistant Home 绝对路径；与 ``assistant_id`` 一起驱动工具过滤。"""
    vocal_mode: str = "direct"
    """ADR-0248: 声带分发模式（``direct`` / ``gated``）。tool.fork 据此追加
    ``send_message`` 声带工具；仅 ``gated`` 生效。"""
    vocal_gate: object | None = None
    """ADR-0248: 门控声带实例（``vocal_mode=="gated"`` 时由 runtime loop 注入）。"""
    auto_review_mode: str = "off"
    """ADR-0248: 工具副作用自动审查模式（``off`` / ``shadow`` / ``enforce``）。"""
    auto_review_gate: object | None = None
    """ADR-0248: ``AutoReviewGate`` 实例（``auto_review_mode != "off"`` 时由 runtime
    loop 注入），tool.fork 用它包装副作用工具。"""
    origin: str = "user"
    """ADR-0248: 执行者身份（``user`` / ``subagent`` / ``workflow``）。子代理经
    ``VocalToolFilter`` 物理禁声，绝不对用户发声。"""
    box_accessor: object | None = None
    """ADR-0248: 员工电脑（``/home/box``）访问器实例，供员工机工具消费。"""


class ForkedTools(BaseModel):
    """Per-run tool list with explicit binding provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)
    items: tuple[Tool, ...]
    binding_keys: frozenset[str]


class RoleSnapshot(BaseModel):
    """RoleProfile + team_awareness frozen pair."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)
    profile: RoleProfile
    team_awareness: TeamAwareness | None = None


class ReasonerBundle(BaseModel):
    """agent.reasoning.turn 4-DTO internal bundle (NOT a cross-graph boundary)."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)
    tools: ForkedTools
    role: RoleSnapshot
    context: ReasonerContext
    template: TemplateSelection


class ProceduralMemoryCandidate(BaseModel):
    """Candidate procedural memory (SOP / skill) identified during reflection.

    ADR-0244: Emitted purely from universal cognitive meta-features (multi-step tool
    success chain, artifact generation) without hardcoded skill names or intent regexes.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)
    candidate_id: str
    workflow_summary: str
    tool_sequence: tuple[str, ...] = ()
    evidence_count: int = 1
    confidence: float = 1.0
    suggested_title: str = ""


__all__ = [
    "BindingsView",
    "ForkedTools",
    "MemoryReceipt",
    "ProceduralMemoryCandidate",
    "ReasonerBundle",
    "ReasonerContext",
    "RoleSnapshot",
    "StopPayload",
    "TemplateSelection",
]

# Resolve forward references from TYPE_CHECKING at import time. Each DTO
# references types that live in other contracts modules; without this call
# pydantic raises PydanticUserError on first instantiation.
ReasonerContext.model_rebuild()
TemplateSelection.model_rebuild()
MemoryReceipt.model_rebuild()
StopPayload.model_rebuild()
BindingsView.model_rebuild()
ForkedTools.model_rebuild()
RoleSnapshot.model_rebuild()
ReasonerBundle.model_rebuild()
ProceduralMemoryCandidate.model_rebuild()
