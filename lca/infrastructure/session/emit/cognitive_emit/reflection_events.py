"""Brain-internal spine EP emitters (ADR-0194 P1-15, ADR-0220 §6.2).

Single production seam for ``critic.*``, ``synthesizer.*``,
``skill_router.*``, ``prompt_assembler.*`` and ``reasoner.*`` spine facts
(via ``publish_ep_bound``), plus the reasoner spine envelope. All helpers
no-op when no Session is bound (tests / offline).
"""

from __future__ import annotations

import contextlib
from collections.abc import Sequence
from typing import Any, cast

from lca.contracts.models.cognition.boundary import (
    ForkedTools,
    ReasonerContext,
    RoleSnapshot,
    TemplateSelection,
)
from lca.contracts.models.cognition.prompt_assembly import _coerce_decision_path
from lca.contracts.models.cognition.reasoner_turn import ReasonerTurnPlan, ReasonerTurnRender
from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols import Reasoner, Tool
from lca.infrastructure.session.emit.cognitive_emit.envelope import (
    AppendReceipt,
    publish_ep_bound,
)


def emit_critic_eval_start_for_state(
    state: AgentState,
    *,
    session: object | None = None,
    actor: str = "critic",
) -> AppendReceipt | None:
    """Append one ``critic.eval.start`` spine fact."""
    return publish_ep_bound(
        "critic.eval.start",
        {"state_id": state.trace_id},
        state=state,
        session=session,
        actor=actor,
    )


def emit_critic_eval_end_for_state(
    state: AgentState,
    *,
    outcome: str = "success",
    session: object | None = None,
    actor: str = "critic",
) -> AppendReceipt | None:
    """Append one ``critic.eval.end`` spine fact."""
    return publish_ep_bound(
        "critic.eval.end",
        {"state_id": state.trace_id, "outcome": outcome},
        state=state,
        session=session,
        actor=actor,
    )


def emit_synthesizer_merge_for_state(
    *,
    state_id: str,
    candidate_count: int,
    outcome: str = "success",
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "synthesizer",
) -> AppendReceipt | None:
    """Append one ``synthesizer.merge`` spine fact."""
    return publish_ep_bound(
        "synthesizer.merge",
        {"state_id": state_id, "candidate_count": candidate_count, "outcome": outcome},
        state=state,
        session=session,
        actor=actor,
    )


def emit_skill_router_route_for_state(
    *,
    state_id: str,
    template: str,
    decision_path: str | None = None,
    outcome: str = "success",
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "skill_router",
) -> AppendReceipt | None:
    """Append one ``skill_router.route`` spine fact."""
    payload: dict[str, Any] = {
        "state_id": state_id,
        "template": template,
        "outcome": outcome,
    }
    if decision_path is not None:
        payload["decision_path"] = decision_path
    return publish_ep_bound(
        "skill_router.route",
        payload,
        state=state,
        session=session,
        actor=actor,
    )


def _prompt_assembler_start_payload(plan: ReasonerTurnPlan) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "state_id": plan.state_id,
        "template_id": plan.template_id,
    }
    if plan.sections_preview:
        payload["sections"] = list(plan.sections_preview)
    if plan.decision_path is not None:
        payload["decision_path"] = plan.decision_path
    if plan.activated_skill_ids:
        payload["activated_skills"] = list(plan.activated_skill_ids)
    payload["tools_count"] = plan.tools_count
    payload["available_skills_count"] = plan.available_skills_count
    if plan.variant_preview is not None:
        payload["variant"] = plan.variant_preview
    return payload


def _prompt_assembler_end_payload(
    plan: ReasonerTurnPlan,
    render: ReasonerTurnRender | None,
    *,
    outcome: str,
    section_count: int = 0,
    variant: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "state_id": plan.state_id,
        "template_id": plan.template_id,
        "section_count": section_count,
        "outcome": outcome,
    }
    if render is not None:
        if render.section_outputs is not None:
            payload["section_outputs"] = [
                {k: v for k, v in dict(item).items() if v is not None}
                for item in render.section_outputs
            ]
        if render.total_chars is not None:
            payload["total_chars"] = render.total_chars
    resolved_variant = variant
    if resolved_variant is None and render is not None:
        resolved_variant = render.variant
    if resolved_variant is None:
        resolved_variant = plan.variant_preview
    if resolved_variant is not None:
        payload["variant"] = resolved_variant
    return payload


def emit_prompt_assembler_start_for_state(
    state: AgentState,
    plan: ReasonerTurnPlan,
    *,
    session: object | None = None,
    actor: str = "reasoner",
) -> AppendReceipt | None:
    """Append one ``prompt_assembler.assemble.start`` spine fact."""
    return publish_ep_bound(
        "prompt_assembler.assemble.start",
        _prompt_assembler_start_payload(plan),
        state=state,
        session=session,
        actor=actor,
    )


def emit_prompt_assembler_end_for_state(
    state: AgentState,
    plan: ReasonerTurnPlan,
    render: ReasonerTurnRender | None,
    *,
    outcome: str = "success",
    section_count: int | None = None,
    variant: str | None = None,
    session: object | None = None,
    actor: str = "reasoner",
) -> AppendReceipt | None:
    """Append one ``prompt_assembler.assemble.end`` spine fact."""
    resolved_count = section_count
    if resolved_count is None and render is not None:
        resolved_count = render.section_count
    if resolved_count is None:
        resolved_count = 0
    return publish_ep_bound(
        "prompt_assembler.assemble.end",
        _prompt_assembler_end_payload(
            plan,
            render,
            outcome=outcome,
            section_count=resolved_count,
            variant=variant,
        ),
        state=state,
        session=session,
        actor=actor,
    )


def emit_reasoner_reason_start_for_state(
    state: AgentState,
    *,
    state_id: str | None = None,
    session: object | None = None,
    actor: str = "reasoner",
) -> AppendReceipt | None:
    """Append one ``reasoner.reason.start`` spine fact."""
    return publish_ep_bound(
        "reasoner.reason.start",
        {"state_id": state_id or state.trace_id},
        state=state,
        session=session,
        actor=actor,
    )


def emit_reasoner_reason_end_for_state(
    state: AgentState,
    *,
    outcome: str = "success",
    state_id: str | None = None,
    session: object | None = None,
    actor: str = "reasoner",
) -> AppendReceipt | None:
    """Append one ``reasoner.reason.end`` spine fact."""
    return publish_ep_bound(
        "reasoner.reason.end",
        {"state_id": state_id or state.trace_id, "outcome": outcome},
        state=state,
        session=session,
        actor=actor,
    )


def _emit_reasoner_meta_from_render(plan: ReasonerTurnPlan, render: ReasonerTurnRender) -> None:
    from lca.infrastructure.observability.meta_event_emit import (
        emit_context_injected,
        emit_prompt_sections_from_trace,
    )

    if render.section_outputs:
        emit_prompt_sections_from_trace(
            template_id=plan.template_id,
            sections=list(render.section_outputs),
        )
    for skill_id in render.activated_skill_ids:
        emit_context_injected(
            source=f"skill:{skill_id}",
            content_ref=f"skill:{skill_id}@prompt",
            model_visible=True,
        )


async def run_reasoner_generate_thoughts_with_spine_facts(
    reasoner: Reasoner,
    state: AgentState,
    tools: Sequence[Tool] | ForkedTools | None = None,
) -> LLMResponse:
    """Run ``Reasoner`` with reasoner spine EPs via FactGateway.

    ADR-0220 §6.2 P9 slimmed :class:`PromptReasoner` to ``render_turn`` +
    ``complete_turn`` only — turn planning / ``generate_thoughts``
    moved out. Turn planning is now a graph-node concern (P4); here we
    synthesize an empty ``ReasonerTurnPlan`` so the existing EP envelope
    keeps working without requiring the caller to thread a plan in.

    Both ``render_turn`` and ``complete_turn`` are mandatory; missing
    either raises :class:`AttributeError` (no fallback path remains).

    The start EP fires *after* ``render_turn`` resolves so the payload
    carries the actual ``template_id`` picked by the reasoner's selector.
    """
    render_turn = getattr(reasoner, "render_turn", None)
    complete_turn = getattr(reasoner, "complete_turn", None)
    if not callable(render_turn) or not callable(complete_turn):
        raise AttributeError(
            "Reasoner must implement render_turn(context, template, role) "
            "and complete_turn(state, render); got "
            f"render_turn={callable(render_turn)}, "
            f"complete_turn={callable(complete_turn)}"
        )

    role_profile = getattr(reasoner, "role_profile", None)
    if role_profile is None:
        raise AttributeError(
            "Reasoner must expose role_profile (boot-time seam) to build "
            "the typed RoleSnapshot boundary DTO."
        )

    plan: ReasonerTurnPlan = ReasonerTurnPlan(
        state_id=state.trace_id,
        template_id="",
        decision_path="legacy",
        activated_skill_ids=(),
        tools_count=0,
        available_skills_count=0,
        sections_preview=(),
        variant_preview=None,
    )
    reasoner_context = ReasonerContext(
        task=state.task or "",
        activated_skills=tuple(state.activated_skills),
        manifest=None,
    )
    template_selection = TemplateSelection(
        template_id=plan.template_id,
        variant="react",
        decision_path=plan.decision_path,
    )
    role_snapshot = RoleSnapshot(
        profile=role_profile,
        team_awareness=state.team_awareness,
    )
    try:
        render: ReasonerTurnRender = cast(
            "ReasonerTurnRender",
            render_turn(reasoner_context, template_selection, role_snapshot),
        )
    except BaseException:
        with contextlib.suppress(Exception):
            emit_prompt_assembler_start_for_state(state, plan)
            emit_prompt_assembler_end_for_state(
                state,
                plan,
                None,
                outcome="failure",
                section_count=0,
                variant=plan.variant_preview,
            )
        raise
    # Backfill the plan with the actual template/decision-path/variant the
    # reasoner resolved at render time, so the EP payloads carry truthful
    # values even when turn-planning is upstream of this entry point (P4).
    rendered_template_id = (
        render.trace.template_id if render.trace is not None else plan.template_id
    )
    # The trace carries the raw selector string; coerce to the closed
    # SelectorDecisionPath vocabulary (unknown -> "legacy", the canonical
    # semantic in prompt_assembly).
    rendered_decision_path = (
        _coerce_decision_path(render.trace.selector_decision_path)
        if render.trace is not None
        else plan.decision_path
    )
    rendered_sections_preview = (
        tuple(s.name for s in render.trace.sections)
        if render.trace is not None
        else plan.sections_preview
    )
    plan = ReasonerTurnPlan(
        state_id=plan.state_id,
        template_id=rendered_template_id,
        decision_path=rendered_decision_path,
        activated_skill_ids=render.activated_skill_ids,
        tools_count=plan.tools_count,
        available_skills_count=plan.available_skills_count,
        sections_preview=rendered_sections_preview,
        variant_preview=render.variant,
    )
    with contextlib.suppress(Exception):
        emit_prompt_assembler_start_for_state(state, plan)
    with contextlib.suppress(Exception):
        emit_prompt_assembler_end_for_state(state, plan, render, outcome="success")
    with contextlib.suppress(Exception):
        _emit_reasoner_meta_from_render(plan, render)
    with contextlib.suppress(Exception):
        emit_reasoner_reason_start_for_state(state, state_id=plan.state_id)
    try:
        # NOTE: complete_turn requires explicit tools (no silent fallback);
        # the deprecated seam has no fork, so an explicit empty list is passed
        # when the caller provides none.
        response = await cast(
            "Any", complete_turn(state, render, tools if tools is not None else [])
        )
    except BaseException:
        with contextlib.suppress(Exception):
            emit_reasoner_reason_end_for_state(
                state,
                outcome="failure",
                state_id=plan.state_id,
            )
        raise
    with contextlib.suppress(Exception):
        emit_reasoner_reason_end_for_state(state, outcome="success", state_id=plan.state_id)
    return cast("LLMResponse", response)


__all__ = [
    "emit_critic_eval_end_for_state",
    "emit_critic_eval_start_for_state",
    "emit_prompt_assembler_end_for_state",
    "emit_prompt_assembler_start_for_state",
    "emit_reasoner_reason_end_for_state",
    "emit_reasoner_reason_start_for_state",
    "emit_skill_router_route_for_state",
    "emit_synthesizer_merge_for_state",
    "run_reasoner_generate_thoughts_with_spine_facts",
]
