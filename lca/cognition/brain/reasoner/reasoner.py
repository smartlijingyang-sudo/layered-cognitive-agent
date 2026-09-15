"""PromptReasoner — typed DTO seam between concept.prompt.render and LLM call.

Solo / member / lead share the same Reasoner (ADR-0035); per-turn rendering
flows through typed boundary DTOs (ADR-0220 §6 P4):

  ``render_turn(context, template, role, template_provider) -> ReasonerTurnRender``
  ``complete_turn(state, render, tools) -> LLMResponse``

Boot-time constructor dependencies are limited to injected ports
(``llm`` / ``selector`` / ``template_provider``). Role identity arrives as
``RoleSnapshot``; per-turn tools arrive as ``ForkedTools`` (or a tool
sequence). PromptReasoner does **not** own RoleProfile assembly or a
boot-time tools list — those belong at the Cordis/Profile → Bindings →
``concept.tool.fork`` boundary (eng/retire-v1-reasoner-sandbox).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from lca.cognition.brain.llm_turn import execute_llm_turn
from lca.cognition.brain.sections.assembler import render_template
from lca.contracts.models.cognition.boundary import (
    ForkedTools,
    ReasonerContext,
    RoleSnapshot,
    TemplateSelection,
)
from lca.contracts.models.cognition.prompt_assembly import (
    PromptSectionRegistry,
    PromptTemplateProvider,
    PromptTemplateSelector,
    PromptTrace,
    normalize_selector_result,
)
from lca.contracts.models.cognition.reasoner_turn import (
    ReasonerTurnPlan,
    ReasonerTurnRender,
)
from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.observability import sha256_payload_digest as _sha256_digest
from lca.contracts.protocols import LLMAdapter, Tool


def _section_output_dicts(trace: PromptTrace) -> tuple[dict[str, Any], ...]:
    """Render a PromptTrace's per-section breakdown as immutable dicts."""
    return tuple(
        {
            "name": s.name,
            "kind": s.kind,
            "optional": s.optional,
            "used_fallback": s.used_fallback,
            "skipped_empty": s.skipped_empty,
            "text_chars": s.text_chars,
            "text": s.text,
            "content_digest": _sha256_digest(s.text) if s.text else None,
        }
        for s in trace.sections
    )


def _coerce_tools(tools: Sequence[Tool] | ForkedTools) -> tuple[Tool, ...]:
    """Accept ForkedTools or a raw sequence; reject None at the call site."""
    if isinstance(tools, ForkedTools):
        return tuple(tools.items)
    return tuple(tools)


class PromptReasoner:
    """Render the prompt from typed boundary DTOs, then call the LLM.

    SRP: consume injected ports + boundary DTOs only. No RoleProfile /
    tools assembly state on the instance.
    """

    def __init__(
        self,
        llm: LLMAdapter,
        *,
        selector: PromptTemplateSelector | None = None,
        template_provider: PromptTemplateProvider | None = None,
        section_registry: PromptSectionRegistry | None = None,
    ) -> None:
        self.llm = llm
        self.selector: PromptTemplateSelector | None = selector
        self._template_provider: PromptTemplateProvider | None = template_provider
        self._section_registry: PromptSectionRegistry | None = section_registry

    def build_turn_plan(self, state: AgentState) -> ReasonerTurnPlan:
        """Derive pre-render plan from state; selectors override template_id."""
        manifest = getattr(state, "context", None)
        activated = tuple(getattr(manifest, "activated_skill_ids", ()) or ())
        tools_count = len(getattr(state, "tools", ()) or ())
        if self.selector is None:
            raise RuntimeError(
                "PromptReasoner.build_turn_plan: PromptTemplateSelector "
                "is not wired; concept.template.select must populate "
                "TemplateSelection before build_turn_plan."
            )
        template_id, decision_path = normalize_selector_result(
            self.selector.select(state=state)
        )
        if not template_id:
            raise RuntimeError(
                "PromptReasoner.build_turn_plan: selector returned empty "
                "template_id; concept.template.select must pick a non-empty id."
            )
        return ReasonerTurnPlan(
            state_id=getattr(state, "trace_id", "") or "",
            template_id=template_id,
            decision_path=decision_path,
            activated_skill_ids=activated,
            tools_count=tools_count,
            available_skills_count=len(activated),
            sections_preview=(),
            variant_preview=None,
        )

    def render_turn(
        self,
        context: ReasonerContext,
        template: TemplateSelection,
        role: RoleSnapshot,
        template_provider: PromptTemplateProvider | None = None,
    ) -> ReasonerTurnRender:
        """Render a prompt from typed boundary DTOs (no AgentState reads)."""
        template_id = template.template_id
        decision_path = template.decision_path
        if not template_id:
            if self.selector is None:
                raise RuntimeError(
                    "PromptReasoner.render_turn: empty template_id and no "
                    "PromptTemplateSelector wired; concept.template.select "
                    "must populate TemplateSelection before render_turn."
                )
            selected_id, selected_path = normalize_selector_result(
                self.selector.select(state=_empty_state_for_selector())
            )
            template_id = selected_id
            decision_path = selected_path

        provider = template_provider if template_provider is not None else self._template_provider
        if provider is None:
            raise RuntimeError(
                "PromptReasoner.render_turn needs template_provider; "
                "pass it explicitly or inject it at Cordis compose boot."
            )
        tpl = provider.get_template(template_id)
        if tpl is None:
            from lca.contracts.models.cognition.prompt_assembly import (
                MissingPromptSectionError,
            )

            raise MissingPromptSectionError(template_id, "pure")
        prompt, trace = render_template(
            template=tpl,
            registry=self._section_registry,
            role_profile=role.profile,
            awareness=role.team_awareness,
            manifest=context.manifest,
            tools=(),
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
        tools: Sequence[Tool] | ForkedTools,
    ) -> LLMResponse:
        """Invoke the LLM for one rendered turn.

        ``tools`` is required — there is no silent fallback to a boot-time
        empty tools list when ``concept.tool.fork`` failed or was skipped.
        """
        if tools is None:  # type: ignore[comparison-overlap]
            raise RuntimeError(
                "PromptReasoner.complete_turn requires per-turn tools "
                "(ForkedTools or Sequence[Tool]); boot empty-tools fallback "
                "is retired (eng/retire-v1-reasoner-sandbox)."
            )
        effective_tools = _coerce_tools(tools)

        # spec section H ContextVar deletion: cursor + reasoner_prompt
        # are passed explicitly via kwargs to ``execute_llm_turn`` →
        # ``llm.complete(cursor=..., reasoner_prompt=...)``; ModelVisibleHookAdapter
        # pops them and forwards to the hook.
        cursor: Any = None
        reasoner_prompt: Any = None
        if render.trace is not None:
            from lca.cognition.body.executor.cursor_record import CursorRecord
            from lca.plugins.events.hooks.model_visible.reasoner_prompt import (
                CurrentReasonerPrompt,
            )

            cursor = CursorRecord.get()
            if cursor is None:
                step_id = f"step-unknown-{render.trace.template_id}"
            else:
                try:
                    step_id = f"step-{cursor.snapshot.step_index + 1:03d}"
                except Exception:
                    step_id = f"step-unknown-{render.trace.template_id}"
            reasoner_prompt = CurrentReasonerPrompt(
                step_id=step_id,
                template_id=render.trace.template_id,
                selector_decision_path=render.trace.selector_decision_path,
                system_prompt_text=render.trace.system_prompt_text,
                prompt_trace=render.trace,
                context_manifest=render.manifest,
            )
        try:
            return await execute_llm_turn(
                self.llm,
                list(effective_tools),
                render.prompt,
                step=state.step,
                state=state,
                task=state.task or "",
                cursor=cursor,
                reasoner_prompt=reasoner_prompt,
            )
        finally:
            pass  # explicit DI; no ContextVar reset needed


def _empty_state_for_selector() -> AgentState:
    """Minimum AgentState for legacy selectors that still expect AgentState."""
    from lca.contracts.models.core.state.state import (
        AgentState as _AgentState,
    )
    from lca.contracts.models.core.state.state import (
        Budget as _Budget,
    )

    return _AgentState(trace_id="reasoner", task="", budget=_Budget())


__all__ = ["PromptReasoner", "_section_output_dicts"]
