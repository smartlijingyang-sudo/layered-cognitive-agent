"""PromptReasoner — call LLM to generate candidate thoughts.

Solo / member / lead 共用同一个 Reasoner（ADR-0035）：状态携带
``TeamAwareness`` 时由 ``PromptTemplateSelector`` 决定模板，
否则走 ``react_prompt``。Reasoner 只负责 LLM 调用；模板渲染由
``PromptAssembler``（通过 ``PromptSectionRegistry`` + ``PromptTemplateProvider``）承担。
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
    render_member_reports,
    render_teammates,
)
from lca.cognition.brain.sections.types import (
    render_prior_conversation_from_state as _prior_conversation_text,
)
from lca.cognition.brain.sections.types import (
    strip_empty_labeled_lines as _strip_empty_prompt_fields,
)
from lca.contracts.atoms.telemetry import ATTR_PROMPT_TEMPLATE
from lca.contracts.models.cognition.prompt_assembly import (
    PromptAssembler,
    PromptTemplateSelector,
    PromptTrace,
    SelectorDecisionPath,
    normalize_assembler_result,
    normalize_selector_result,
)

# ── Legacy helpers retained for tests that import them directly ────
# The sections-based pipeline replaces the inline implementation;
# these helpers stay so characterization tests pin the exact text
# shape. They are *not* used by PromptReasoner itself anymore.
from lca.contracts.models.core.llm import LLMResponse
from lca.contracts.models.core.perception import ContextManifest
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.team.delegation import DelegationResult
from lca.contracts.models.team.role_team import RoleProfile
from lca.contracts.protocols import LLMAdapter, Tool
from lca.infrastructure.observability import annotate
from lca.infrastructure.observability.loop_cursor._capture_io import (
    sha256_digest as _sha256_digest,
)


def build_teammates_text(profiles: Sequence[RoleProfile]) -> str:
    return render_teammates(profiles)


def build_member_reports_text(results: Sequence[DelegationResult]) -> str:
    return render_member_reports(results)


def _role_prompt_vars(
    role_profile: RoleProfile,
    tools_desc: str,
    state: AgentState,
    context_lines: str,
    *,
    tools: Sequence[Tool] | None = None,
    available_skills: str = "",
    manifest: object | None = None,
) -> dict[str, str]:
    """Legacy helper used by characterization tests.

    Renders the full role-keyed variable dict, mirroring the old
    pre-section-manifest implementation so tests that import
    ``_role_prompt_vars`` keep passing.
    """

    from lca.cognition.brain.sandbox_prompt import build_cloud_sandbox_prompt
    from lca.cognition.brain.sections.types import (
        clock_from_state,
        render_artifacts_block,
        render_assigned_roles,
        render_prior_conversation_from_state,
        render_subtasks_block,
    )
    from lca.cognition.brain.sections.types import (
        render_activated_skills as _render_act,
    )

    tool_list = list(tools or [])
    cloud_sandbox = build_cloud_sandbox_prompt(tool_list) if tool_list else ""
    clock = clock_from_state(state)
    current_date = clock.text if clock else ""
    variables: dict[str, str] = {
        "role": role_profile.role,
        "goal": role_profile.goal,
        "backstory": role_profile.backstory,
        "tools": tools_desc,
        "task": state.task,
        "prior_conversation": render_prior_conversation_from_state(state),
        "context": context_lines,
        "available_skills": available_skills or "（无技能库）",
        "activated_skills": _render_act(state),
        "search_routing": "",
        "cloud_sandbox": cloud_sandbox,
    }
    if current_date:
        variables["current_date"] = current_date
    else:
        variables["current_date"] = ""
    subtasks_block = render_subtasks_block(state)
    if subtasks_block:
        variables["context"] = variables["context"] + "\n\n" + subtasks_block
    artifacts_block = render_artifacts_block(state)
    if artifacts_block:
        variables["context"] = variables["context"] + "\n\n" + artifacts_block
    awareness = state.team_awareness
    if awareness is not None:
        variables["teammates"] = render_teammates(awareness.teammates)
        variables["assigned_roles_text"] = render_assigned_roles(awareness.assigned_roles)
        variables["member_reports_text"] = render_member_reports(awareness.results)
        if awareness.consult_duty is not None:
            variables["member_status_text"] = awareness.consult_duty.member_status.as_prompt_text()
            from lca.contracts.models.team.consultation import build_evidence_pack_text

            variables["evidence_pack_text"] = build_evidence_pack_text(
                awareness.consult_duty.outcomes
            )
        else:
            variables["member_status_text"] = ""
            variables["evidence_pack_text"] = ""
    return variables


# ── PromptReasoner ─────────────────────────────────────────────────


class PromptReasoner:
    """Default Reasoner: render the prompt via the assembler, call the LLM.

    Constructor accepts either the **legacy** kwarg set
    ``(tools_desc, templates, available_skills)`` for back-compat with
    existing tests, or the **new** kwarg set
    ``(catalog, assembler, selector, tools)`` for production wiring.
    Both shapes are tolerated so we can land the section-manifest split
    without rewriting every test at once.
    """

    def __init__(
        self,
        llm: LLMAdapter,
        role_profile: RoleProfile,
        tools_desc_or_catalog: str | object | None = None,
        *,
        # New-shape kwargs (preferred):
        assembler: PromptAssembler | None = None,
        selector: PromptTemplateSelector | None = None,
        # Legacy kwargs (kept for the existing test surface):
        tools_desc: str | None = None,
        tools: Sequence[Tool] | None = None,
        templates: dict[str, str] | None = None,
        available_skills: str = "",
    ) -> None:
        self.llm = llm
        self.role_profile = role_profile
        if isinstance(tools_desc_or_catalog, str):
            self.tools_desc = tools_desc_or_catalog
            self.catalog = None
        elif tools_desc_or_catalog is None:
            # Callers using the legacy kwarg form (e.g. ``tools_desc="..."``)
            # may omit the third positional argument; fall back to the kwarg.
            self.tools_desc = tools_desc or ""
            self.catalog = None
        else:
            self.catalog = tools_desc_or_catalog
            self.tools_desc = tools_desc or ""
        self.assembler: PromptAssembler | None = assembler
        self.selector: PromptTemplateSelector | None = selector
        self.tools: list[Tool] = list(tools) if tools else []
        self._legacy_templates: dict[str, str] = dict(templates or {})
        self.available_skills = available_skills

    # Legacy hooks — preserved verbatim so older tests keep compiling.
    def register_template(self, name: str, template: str) -> None:
        self._legacy_templates[name] = template

    async def generate_thoughts(self, state: AgentState) -> LLMResponse:
        from lca.contracts.models.core.perceive_state import PerceiveState

        manifest = PerceiveState.from_agent_state(state).current_manifest
        template_id, decision_path = self._select_template(state)
        annotate(**{ATTR_PROMPT_TEMPLATE: template_id})

        from lca.plugins.events.publishers.spine_reflector_cognition import (
            emit_prompt_assembler_end,
            emit_prompt_assembler_start,
            emit_reasoner_reason_end,
            emit_reasoner_reason_start,
        )

        state_id = state.trace_id
        # 渲染前的真实激活集（start EP 不再发空预览）；end EP 用
        # trace.activated_skill_ids 权威覆盖。
        activated_skill_ids: tuple[str, ...] = tuple(
            skill.skill_id for skill in state.activated_skills
        )
        tools_count = len(self.tools)
        available_skills_count = self._available_skills_count_hint()
        # Sections preview from the template itself (available pre-render);
        # end EP carries the authoritative section_outputs.
        sections_preview: list[str] = self._template_section_names(template_id)
        variant_preview = self._template_variant(template_id)
        emit_prompt_assembler_start(
            state_id=state_id,
            template_id=template_id,
            decision_path=decision_path,
            sections=sections_preview or None,
            activated_skills=list(activated_skill_ids) or None,
            tools_count=tools_count,
            available_skills_count=available_skills_count,
            variant=variant_preview,
        )
        reasoner_prompt_token = None
        try:
            prompt, trace, section_count = self._render_prompt(
                state,
                manifest=manifest,
                template_id=template_id,
                decision_path=decision_path,
            )
        except BaseException:
            emit_prompt_assembler_end(
                state_id=state_id,
                template_id=template_id,
                section_count=0,
                outcome="failure",
                variant=variant_preview,
            )
            raise
        if trace is not None:
            sections_preview = [s.name for s in trace.sections]
            activated_skill_ids = trace.activated_skill_ids
            tools_count = trace.tools_count
            available_skills_count = trace.available_skills_count
            total_chars = trace.total_chars
            section_outputs = [
                {
                    "name": s.name,
                    "kind": s.kind,
                    "optional": s.optional,
                    "used_fallback": s.used_fallback,
                    "skipped_empty": s.skipped_empty,
                    "text_chars": s.text_chars,
                    # ADR-0176 D3 §5:EP payload 携带渲染正文与摘要，
                    # viewer 无需回读 model_visible 旁路即可重建。
                    "text": s.text,
                    "content_digest": _sha256_digest(s.text) if s.text else None,
                }
                for s in trace.sections
            ]
            reasoner_prompt_token = self._bind_reasoner_prompt(trace, manifest)
        else:
            total_chars = None
            section_outputs = None
        emit_prompt_assembler_end(
            state_id=state_id,
            template_id=template_id,
            section_count=section_count,
            section_outputs=section_outputs,
            total_chars=total_chars,
            outcome="success",
            variant=trace.variant if trace is not None else variant_preview,
        )

        emit_reasoner_reason_start(state_id=state_id)
        try:
            response = await execute_llm_turn(
                self.llm,
                self.tools,
                prompt,
                step=state.step,
                state=state,
                task=state.task or "",
            )
        except BaseException:
            emit_reasoner_reason_end(state_id=state_id, outcome="failure")
            if reasoner_prompt_token is not None:
                self._reset_reasoner_prompt(reasoner_prompt_token)
            raise
        emit_reasoner_reason_end(state_id=state_id, outcome="success")
        if reasoner_prompt_token is not None:
            self._reset_reasoner_prompt(reasoner_prompt_token)
        return response

    def _select_template(self, state: AgentState) -> tuple[str, SelectorDecisionPath]:
        if self.selector is not None:
            result = self.selector.select(state=state)
            return normalize_selector_result(result)
        return self._legacy_select_template(state), "legacy"

    def _render_prompt(
        self,
        state: AgentState,
        *,
        manifest: object | None,
        template_id: str,
        decision_path: SelectorDecisionPath = "legacy",
    ) -> tuple[str, PromptTrace | None, int]:
        if self.assembler is not None:
            result = self.assembler.render(
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
            return prompt, trace, section_count
        # Legacy fallback: substring substitution using the registered
        # templates. Used by tests that still drive ``PromptReasoner``
        # with a plain ``templates={...}`` dict.
        template_name = template_id
        variables = self._legacy_variables(state, manifest=manifest)
        template = self._legacy_templates.get(template_name, "")
        prompt = template.format(**variables) if template else ""
        return prompt, None, 0

    def _available_skills_count_hint(self) -> int:
        catalog = getattr(self, "catalog", None)
        if catalog is None:
            return 0
        installed = getattr(catalog, "installed_skills", None)
        if installed is not None:
            try:
                return len(installed)
            except TypeError:
                return 0
        return 0

    def _template_section_names(self, template_id: str) -> list[str]:
        """Return the names of sections a template references.

        Falls back to an empty list when no assembler/template_provider is
        wired (legacy/test paths). Used by ``emit_prompt_assembler_start``
        so the start EP carries a useful section preview before render.
        """
        assembler = self.assembler
        if assembler is None:
            return []
        provider = getattr(assembler, "template_provider", None)
        if provider is None:
            return []
        template = provider.get_template(template_id)
        if template is None:
            return []
        return [ref.name for ref in template.sections]

    def _template_variant(self, template_id: str) -> str | None:
        """Return the variant a template renders as (pre-render preview).

        Falls back to ``None`` when no assembler/template_provider is wired
        (legacy/test paths); the end EP then carries ``trace.variant``.
        """
        assembler = self.assembler
        if assembler is None:
            return None
        provider = getattr(assembler, "template_provider", None)
        if provider is None:
            return None
        template = provider.get_template(template_id)
        if template is None:
            return None
        return getattr(template, "variant", None)

    def _bind_reasoner_prompt(
        self, trace: PromptTrace, context_manifest: ContextManifest | None
    ) -> Any:
        """Bind the rendered prompt truth into the LLM-boundary ContextVar.

        Precondition: ``trace`` is the PromptTrace produced by this think
        call's assembler render; ``context_manifest`` is the ContextManifest
        read for the same think call (``None`` when perception produced
        none). Ownership: the Reasoner binds and resets around the LLM call;
        the LLM boundary adapter reads prompt_trace / context_manifest to
        make skill/prompt assembly recoverable under model_visible/step_<NN>/
        (ADR-0167 D3/D4). Failures of the optional sidecar write are logged
        and never block the business path (ADR-0169 L10 + D5).
        """
        from lca.infrastructure.observability.loop_cursor.model_visible_binding import (
            get_current_model_visible_capture,
        )
        from lca.plugins.events.hooks.model_visible.reasoner_prompt import (
            CurrentReasonerPrompt,
            bind_current_reasoner_prompt,
        )
        from lca.infrastructure.observability.loop_cursor.reasoner_prompt_capture import (
            StdReasonerPromptCapture,
        )

        # ADR-0175 D3: capture writes system_prompt.json to <run_dir>/model_visible/.
        # We reuse the same run_dir that StdModelVisibleCapture is already bound to
        # (installed by RunSessionBuilder at session build time). When capture
        # is absent (e.g. tests), skip the file write but still bind the
        # ContextVar so downstream code can see the rendered prompt text.
        capture = get_current_model_visible_capture()
        run_dir = getattr(capture, "run_dir", None)
        step_id = self._step_id_for_trace(trace)
        if run_dir is not None:
            try:
                StdReasonerPromptCapture(run_dir=run_dir).capture(step_id=step_id, trace=trace)
            except Exception as exc:  # ADR-0169 L10 + D5: 不挡业务
                import logging as _logging

                _logging.getLogger(__name__).warning("reasoner_prompt_capture_failed: %s", exc)
        return bind_current_reasoner_prompt(
            CurrentReasonerPrompt(
                step_id=step_id,
                template_id=trace.template_id,
                selector_decision_path=trace.selector_decision_path,
                system_prompt_text=trace.system_prompt_text,
                prompt_trace=trace,
                context_manifest=context_manifest,
            )
        )

    @staticmethod
    def _step_id_for_trace(trace: PromptTrace) -> str:
        from lca.infrastructure.observability.loop_cursor.coordinator_adapter import (
            get_current_cursor,
        )

        cursor = get_current_cursor()
        if cursor is None:
            return f"step-unknown-{trace.template_id}"
        try:
            snap = cursor.snapshot
            return f"step-{snap.step_index + 1:03d}"
        except Exception:
            return f"step-unknown-{trace.template_id}"

    @staticmethod
    def _reset_reasoner_prompt(token: Any) -> None:
        from lca.plugins.events.hooks.model_visible.reasoner_prompt import (
            reset_current_reasoner_prompt,
        )

        reset_current_reasoner_prompt(token)

    def _legacy_select_template(self, state: AgentState) -> str:
        if isinstance(getattr(state, "active_template", None), str) and state.active_template:
            return state.active_template
        awareness = state.team_awareness
        if awareness is None:
            return "react_prompt"
        if awareness.consult_duty is not None:
            return "hierarchical_prompt"
        return "routing_prompt"

    def _legacy_variables(self, state: AgentState, *, manifest: object | None) -> dict[str, str]:
        from lca.cognition.brain.sandbox_prompt import build_cloud_sandbox_prompt
        from lca.cognition.brain.sections.types import (
            clock_from_state,
            context_exclusions_for,
            render_activated_skills,
            render_artifacts_block,
            render_assigned_roles,
            render_context_lines,
            render_prior_conversation_from_state,
            render_subtasks_block,
        )

        awareness = state.team_awareness
        exclude = context_exclusions_for(awareness)
        context_lines = render_context_lines(state, exclude_kinds=exclude)
        subtasks_block = render_subtasks_block(state)
        artifacts_block = render_artifacts_block(state)
        if subtasks_block:
            context_lines = context_lines + "\n\n" + subtasks_block
        if artifacts_block:
            context_lines = context_lines + "\n\n" + artifacts_block
        cloud_sandbox = build_cloud_sandbox_prompt(self.tools) if self.tools else ""
        clock = clock_from_state(state)
        current_date = clock.text if clock else ""
        variables: dict[str, str] = {
            "role": self.role_profile.role,
            "goal": self.role_profile.goal,
            "backstory": self.role_profile.backstory,
            "tools": self.tools_desc,
            "task": state.task,
            "prior_conversation": render_prior_conversation_from_state(state),
            "context": context_lines,
            "available_skills": self.available_skills or "（无技能库）",
            "activated_skills": render_activated_skills(state),
            "search_routing": "",
            "cloud_sandbox": cloud_sandbox,
            "current_date": current_date,
        }
        if awareness is not None:
            variables["teammates"] = render_teammates(awareness.teammates)
            variables["assigned_roles_text"] = render_assigned_roles(awareness.assigned_roles)
            variables["member_reports_text"] = render_member_reports(awareness.results)
            if awareness.consult_duty is not None:
                variables["member_status_text"] = (
                    awareness.consult_duty.member_status.as_prompt_text()
                )
                from lca.contracts.models.team.consultation import build_evidence_pack_text

                variables["evidence_pack_text"] = build_evidence_pack_text(
                    awareness.consult_duty.outcomes
                )
            else:
                variables["member_status_text"] = ""
                variables["evidence_pack_text"] = ""
        return variables


__all__ = [
    "PromptReasoner",
    "_context_lines",
    "_format_activated_skills",
    "_prior_conversation_text",
    "_role_prompt_vars",
    "_strip_empty_prompt_fields",
    "build_member_reports_text",
    "build_teammates_text",
]
