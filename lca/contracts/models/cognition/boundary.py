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
    """Output of ``concept.stop.should_check`` → ``agent.run.phase``.

    Carries the loop-back decision: whether the run should continue, the
    focused reason if it should stop, and the final-output reference
    for terminal recording. ``focus_converged`` is the admission flag
    produced by ``stop.focus.converge``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    should_stop: bool
    focus_converged: bool = False
    reason: str | None = None
    final_output_ref: str | None = None


class BindingsView(BaseModel):
    """Per-run bindings from RuntimePlane; replaces ``AgentState._xxx_ref``."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)
    file_store: object | None = None
    sandbox: object | None = None
    skill_store: object | None = None
    machine_resolver: object | None = None
    search: object | None = None
    bindings: object | None = None


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


__all__ = [
    "BindingsView",
    "ForkedTools",
    "MemoryReceipt",
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
