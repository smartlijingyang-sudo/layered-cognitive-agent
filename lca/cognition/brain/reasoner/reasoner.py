"""PromptReasoner — call LLM with a section-manifest-rendered prompt.

Solo / member / lead share the same Reasoner (ADR-0035): state carries
``TeamAwareness`` and ``PromptTemplateSelector`` picks a template,
otherwise ``react_prompt``. Reasoner is the only place that invokes the
LLM; prompt rendering is delegated to ``PromptAssembler``
(``PromptSectionRegistry`` + ``PromptTemplateProvider``).

Public surface (P9, ADR-0220 §6.2):
- ``__init__(llm, role_profile, *, assembler=None, selector=None, tools=())``
- ``render_turn(state, plan) -> ReasonerTurnRender``
- ``complete_turn(state, render) -> LLMResponse``

``render_turn`` / ``complete_turn`` together replace the old
turn-planning-then-render pair: turn planning now belongs to
``business.reasoning.turn`` graph nodes (P4); Reasoner only renders
and calls.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from lca.cognition.brain.llm_turn import execute_llm_turn
from lca.cognition.brain.sections.types import (
    render_activated_skills as _format_activated_skills,
)
from lca.cognition.brain.sections.types import (
    render_context_lines as _context_lines,
)
from lca.cognition.brain.sections.types import (
    render_prior_conversation_from_state as _prior_conversation_text,
)
from lca.cognition.brain.sections.types import (
    render_teammates,
)
from lca.cognition.brain.sections.types import (
    strip_empty_labeled_lines as _strip_empty_prompt_fields,
)
from lca.contracts.models.cognition.prompt_assembly import (
    PromptAssembler,
    PromptTemplateSelector,
)
from lca.contracts.models.cognition.reasoner_turn import ReasonerTurnPlan, ReasonerTurnRender
from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.models.team.role.team import RoleProfile
from lca.contracts.observability import sha256_payload_digest as _sha256_digest
from lca.contracts.protocols import LLMAdapter, Tool


def build_teammates_text(profiles: Sequence[RoleProfile]) -> str:
    return render_teammates(profiles)


# ── PromptReasoner ─────────────────────────────────────────────────


class PromptReasoner:
    """Render the prompt via the assembler, then call the LLM once per turn.

    ADR-0220 §6.2 P9 slimmed the constructor to a single new-shape kwarg set
    and dropped the legacy ``tools_desc`` / ``templates`` / ``available_skills``
    compat path. Per-run tool resolution moves to the ``primitive.llm.call``
    graph node (P5); boot-time tools reach ``complete_turn`` via
    ``tools=``.
    """

    def __init__(
        self,
        llm: LLMAdapter,
        role_profile: RoleProfile,
        *,
        assembler: PromptAssembler | None = None,
        selector: PromptTemplateSelector | None = None,
        tools: Sequence[Tool] | None = None,
    ) -> None:
        self.llm = llm
        self.role_profile = role_profile
        self.assembler: PromptAssembler | None = assembler
        self.selector: PromptTemplateSelector | None = selector
        self.tools: list[Tool] = list(tools) if tools else []

    def render_turn(self, state: AgentState, plan: ReasonerTurnPlan) -> ReasonerTurnRender:
        """Render the prompt and collect post-render spine metadata (no emit)."""
        from lca.contracts.models.cognition.prompt_assembly import (
            normalize_assembler_result,
            normalize_selector_result,
        )
        from lca.contracts.models.core.perceive.projection import current_manifest_from_state

        manifest = current_manifest_from_state(state)
        assembler = self.assembler
        if assembler is None:
            raise RuntimeError(
                "PromptReasoner.render_turn requires a PromptAssembler; "
                "wire one in via the constructor or upgrade to the "
                "section-manifest assembler plugin."
            )
        # When the caller passes an empty plan (e.g. the cognitive_emit
        # spine envelope synthesizes one before turn-planning moves to
        # graph nodes in P4) we ask the selector for the active template.
        # The selector is optional; without it the assembler raises its
        # own template-not-found error.
        template_id = plan.template_id
        decision_path = plan.decision_path
        if not template_id and self.selector is not None:
            selected_id, decision_path = normalize_selector_result(
                self.selector.select(state=state)
            )
            template_id = selected_id
        result = assembler.render(
            template_id=template_id,
            role_profile=self.role_profile,
            state=state,
            awareness=state.team_awareness,
            manifest=manifest,  # type: ignore[arg-type]
            tools=self.tools,
            activated_skills=tuple(state.activated_skills),
            selector_decision_path=decision_path,
        )
        prompt, trace = normalize_assembler_result(result)
        section_count = len(trace.sections) if trace is not None else 0
        if trace is not None:
            activated_skill_ids = trace.activated_skill_ids
            total_chars = trace.total_chars
            section_outputs = tuple(
                {
                    "name": s.name,
                    "kind": s.kind,
                    "optional": s.optional,
                    "used_fallback": s.used_fallback,
                    "skipped_empty": s.skipped_empty,
                    "text_chars": s.text_chars,
                    # ADR-0176 D3 §5:EP payload 携带渲染正文与摘要,
                    # viewer 无需回读 model_visible 旁路即可重建。
                    "text": s.text,
                    "content_digest": _sha256_digest(s.text) if s.text else None,
                }
                for s in trace.sections
            )
            variant = trace.variant
        else:
            activated_skill_ids = plan.activated_skill_ids
            total_chars = None
            section_outputs = None
            variant = plan.variant_preview
        return ReasonerTurnRender(
            prompt=prompt,
            trace=trace,
            section_count=section_count,
            manifest=manifest,
            activated_skill_ids=activated_skill_ids,
            section_outputs=section_outputs,
            total_chars=total_chars,
            variant=variant,
        )

    async def complete_turn(
        self,
        state: AgentState,
        render: ReasonerTurnRender,
    ) -> LLMResponse:
        """Invoke the LLM for one rendered turn (ModelVisible bind stays here).

        ADR-0220 §6.2 P9 keeps ``complete_turn`` here; P5 will move per-run
        tool resolution to the ``primitive.llm.call`` graph node. For P2 we
        use the boot-time ``self.tools`` list.
        """
        # ADR-0220 §6.3 (P4 plan): bind/reset migrate into the
        # ``primitive.llm.call`` graph node so ModelVisible hook reads the
        # bound prompt via the same ContextVar without reasoner coupling.
        # Until then Reasoner owns the bind around the LLM call.
        # ADR-0185 PR-4 收口:旧 capture 旁路文件落盘退场;system prompt
        # 原文由 ModelVisibleHook 在 LLM 边界走 spine event bus 发
        # ``spine.llm.request.header``,reasoner 侧不再写盘。
        from lca.infrastructure.observability.loop_cursor.coordinator.adapter import (
            get_current_cursor,
        )
        from lca.plugins.events.hooks.model_visible.reasoner_prompt import (
            CurrentReasonerPrompt,
            bind_current_reasoner_prompt,
            reset_current_reasoner_prompt,
        )

        token: Any = None
        if render.trace is not None:
            cursor = get_current_cursor()
            if cursor is None:
                step_id = f"step-unknown-{render.trace.template_id}"
            else:
                try:
                    step_id = f"step-{cursor.snapshot.step_index + 1:03d}"
                except Exception:
                    step_id = f"step-unknown-{render.trace.template_id}"
            token = bind_current_reasoner_prompt(
                CurrentReasonerPrompt(
                    step_id=step_id,
                    template_id=render.trace.template_id,
                    selector_decision_path=render.trace.selector_decision_path,
                    system_prompt_text=render.trace.system_prompt_text,
                    prompt_trace=render.trace,
                    context_manifest=render.manifest,
                )
            )
        try:
            return await execute_llm_turn(
                self.llm,
                list(self.tools),
                render.prompt,
                step=state.step,
                state=state,
                task=state.task or "",
            )
        finally:
            if token is not None:
                reset_current_reasoner_prompt(token)


__all__ = [
    "PromptReasoner",
    "_context_lines",
    "_format_activated_skills",
    "_prior_conversation_text",
    "_strip_empty_prompt_fields",
    "build_teammates_text",
]
