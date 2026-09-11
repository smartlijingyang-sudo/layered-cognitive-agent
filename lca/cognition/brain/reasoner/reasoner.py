"""PromptReasoner — typed DTO seam between concept.prompt.render and LLM call.

Solo / member / lead share the same Reasoner (ADR-0035); per-turn rendering
flows through typed boundary DTOs (ADR-0220 §6 P4):

  ``render_turn(context, template, role) -> ReasonerTurnRender``
  ``complete_turn(state, render) -> LLMResponse``

P4 strips state out of ``render_turn``: a typed ``ReasonerContext`` carries
``task`` / ``activated_skills`` / ``manifest``; a typed ``TemplateSelection``
carries ``template_id`` / ``variant`` / ``decision_path``; a typed
``RoleSnapshot`` carries ``profile`` + ``team_awareness``. The
``concept.prompt.render`` graph feeds those three DTOs in and consumes the
``ReasonerTurnRender`` that ``render_turn`` returns.

Boot-time constructor dependencies are limited to the LLM and the role
profile. Per-run tools arrive as the typed ``ForkedTools`` boundary on
``complete_turn`` once ``primitive.llm.call`` lands (P5); until then the
boot-time ``tools`` list remains the safe default. The ModelVisible
``CurrentReasonerPrompt`` ContextVar bind around the LLM call migrates
into the ``primitive.llm.call`` graph node alongside the tool fork.

The ``selector`` seam stays as a tolerance shim for the legacy
``phase.think.reason.render`` adapter: when callers pass an empty
``TemplateSelection`` the reasoner asks the selector for the active
template id + decision path. ``template_provider`` is the typed seam that
the ``concept.prompt.render`` graph expects.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from lca.cognition.brain.llm_turn import execute_llm_turn
from lca.cognition.brain.sections.assembler import render_template
from lca.contracts.models.cognition.boundary import (
    ReasonerContext,
    RoleSnapshot,
    TemplateSelection,
)
from lca.contracts.models.cognition.prompt_assembly import (
    PromptTemplateProvider,
    PromptTemplateSelector,
    PromptTrace,
)
from lca.contracts.models.cognition.reasoner_turn import ReasonerTurnRender
from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.models.team.role.team import RoleProfile
from lca.contracts.observability import sha256_payload_digest as _sha256_digest
from lca.contracts.protocols import LLMAdapter, Tool


def _section_output_dicts(trace: PromptTrace) -> tuple[dict[str, Any], ...]:
    """Render a PromptTrace's per-section breakdown as immutable dicts.

    ``ReasonerTurnRender.section_outputs`` is a typed tuple of frozen
    dicts; we build it here so the renderer contract does not leak
    ``SectionTrace`` outside the assembler boundary.
    """
    return tuple(
        {
            "name": s.name,
            "kind": s.kind,
            "optional": s.optional,
            "used_fallback": s.used_fallback,
            "skipped_empty": s.skipped_empty,
            "text_chars": s.text_chars,
            # ADR-0176 D3 §5:EP payload 携带渲染正文与摘要,viewer 无需回读
            # model_visible 旁路即可重建。
            "text": s.text,
            "content_digest": _sha256_digest(s.text) if s.text else None,
        }
        for s in trace.sections
    )


# ── PromptReasoner ─────────────────────────────────────────────────


class PromptReasoner:
    """Render the prompt from typed boundary DTOs, then call the LLM.

    ADR-0220 §6 P4 slimmed ``render_turn`` to a pure typed-DTO function:
    ``(context, template, role) -> ReasonerTurnRender``. The reasoner
    no longer reads ``AgentState`` to render — the caller (the
    ``concept.prompt.render`` graph or the legacy
    ``phase.think.reason.render`` adapter) is responsible for assembling
    the boundary DTOs. ``complete_turn`` still needs ``AgentState`` for
    the step cursor and the working task string; that boundary moves to
    ``primitive.llm.call`` (P5), at which point ``state`` disappears
    from the reasoner surface entirely.
    """

    def __init__(
        self,
        llm: LLMAdapter,
        role_profile: RoleProfile,
        *,
        selector: PromptTemplateSelector | None = None,
        template_provider: PromptTemplateProvider | None = None,
        tools: Sequence[Tool] | None = None,
    ) -> None:
        self.llm = llm
        self.role_profile = role_profile
        self.selector: PromptTemplateSelector | None = selector
        self.template_provider: PromptTemplateProvider | None = template_provider
        self.tools: list[Tool] = list(tools) if tools else []

    def render_turn(
        self,
        context: ReasonerContext,
        template: TemplateSelection,
        role: RoleSnapshot,
    ) -> ReasonerTurnRender:
        """Render a prompt from typed boundary DTOs (no AgentState reads).

        ``context`` carries ``task`` / ``activated_skills`` / ``manifest``
        (this turn's perceive output). ``template`` carries the picked
        template id + variant + selector decision path.
        ``role`` carries ``profile`` + ``team_awareness``.

        When ``template.template_id`` is empty (callers that have not
        yet migrated to ``concept.template.select``) we ask
        ``self.selector`` for the active template. Empty template id
        with no selector wired raises ``RuntimeError`` so the render
        graph can fail loud at boot instead of silently falling back.
        """
        template_id = template.template_id
        decision_path = template.decision_path
        if not template_id:
            if self.selector is None:
                raise RuntimeError(
                    "PromptReasoner.render_turn: empty template_id and no "
                    "PromptTemplateSelector wired; concept.template.select "
                    "must populate TemplateSelection before render_turn."
                )
            from lca.contracts.models.cognition.prompt_assembly import (
                normalize_selector_result,
            )

            selected_id, selected_path = normalize_selector_result(
                self.selector.select(state=_empty_state_for_selector())
            )
            template_id = selected_id
            decision_path = selected_path

        if self.template_provider is None:
            raise RuntimeError(
                "PromptReasoner.render_turn needs template_provider (P4 path); "
                "wire one through the constructor or via PROMPT_TEMPLATE_PROVIDER."
            )
        return self._render_with_template(context, role, template_id, decision_path)

    def _render_with_template(
        self,
        context: ReasonerContext,
        role: RoleSnapshot,
        template_id: str,
        decision_path: Any,
    ) -> ReasonerTurnRender:
        provider = self.template_provider
        if provider is None:
            raise RuntimeError(
                "PromptReasoner._render_with_template called without "
                "template_provider; check render_turn's precondition."
            )
        template = provider.get_template(template_id)
        if template is None:
            from lca.contracts.models.cognition.prompt_assembly import (
                MissingPromptSectionError,
            )

            raise MissingPromptSectionError(template_id, "pure")
        prompt, trace = render_template(
            template=template,
            role_profile=role.profile,
            awareness=role.team_awareness,
            manifest=context.manifest,
            tools=tuple(self.tools),
            activated_skills=context.activated_skills,
            selector_decision_path=decision_path,
        )
        if trace is None:
            return ReasonerTurnRender(
                prompt=prompt,
                trace=None,
                section_count=0,
                manifest=None,
                activated_skill_ids=(),
                section_outputs=None,
                total_chars=None,
                variant=None,
            )
        return ReasonerTurnRender(
            prompt=prompt,
            trace=trace,
            section_count=len(trace.sections),
            manifest=None,
            activated_skill_ids=trace.activated_skill_ids,
            section_outputs=_section_output_dicts(trace),
            total_chars=trace.total_chars,
            variant=trace.variant,
        )

    async def complete_turn(
        self,
        state: AgentState,
        render: ReasonerTurnRender,
    ) -> LLMResponse:
        """Invoke the LLM for one rendered turn (ModelVisible bind stays here).

        ADR-0220 §6.2 P9 keeps ``complete_turn`` here; P5 moves per-run
        tool resolution to ``primitive.llm.call``. The ModelVisible bind
        around ``execute_llm_turn`` migrates to that node in P5.
        """
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


def _empty_state_for_selector() -> AgentState:
    """Build the minimum AgentState the legacy selector Protocol expects.

    Selectors that have not migrated to ``ReasonerContext`` still
    ask for ``AgentState``. We construct an empty state with no
    active records; selectors that actually read records will
    short-circuit on the empty inputs.
    """
    from lca.contracts.models.core.state.state import (
        AgentState as _AgentState,
    )
    from lca.contracts.models.core.state.state import (
        Budget as _Budget,
    )

    return _AgentState(trace_id="reasoner", task="", budget=_Budget())


__all__ = ["PromptReasoner", "_section_output_dicts"]
