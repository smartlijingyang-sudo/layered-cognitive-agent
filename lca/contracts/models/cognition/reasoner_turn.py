"""Reasoner turn plan/render DTOs (ADR-0194 P1-15).

Cognition prepares pure turn metadata; infrastructure emits spine EPs via
``publish_ep_bound`` without importing cognition implementations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.models.cognition.prompt_assembly import (
    PromptTrace,
    SelectorDecisionPath,
)
from lca.contracts.models.core.perceive.perception import ContextManifest


@dataclass(frozen=True, slots=True)
class ReasonerTurnPlan:
    """Pre-render metadata for ``prompt_assembler.assemble.start``."""

    state_id: str
    template_id: str
    decision_path: SelectorDecisionPath
    activated_skill_ids: tuple[str, ...]
    tools_count: int
    available_skills_count: int
    sections_preview: tuple[str, ...]
    variant_preview: str | None


@dataclass(frozen=True, slots=True)
class ReasonerTurnRender:
    """Post-render metadata for assembler end EPs and LLM invocation.

    ADR-0220 §4.2: this DTO is the cross-graph boundary between
    ``concept.prompt.render`` (concept graph) and ``agent.reasoning.turn``
    → ``primitive.llm.call``. ``frozen=True`` enforces the closed boundary;
    the dataclass constructor rejects unknown kwargs (extra=forbid equivalent).
    All fields are documented; no surprise fields can sneak through.
    """

    prompt: str
    trace: PromptTrace | None
    section_count: int
    manifest: ContextManifest | None
    activated_skill_ids: tuple[str, ...]
    section_outputs: tuple[dict[str, Any], ...] | None
    total_chars: int | None
    variant: str | None


__all__ = ["ReasonerTurnPlan", "ReasonerTurnRender"]
