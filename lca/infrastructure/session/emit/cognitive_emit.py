"""Gate / perceive / think Session fact production (ADR-0191 R2, ADR-0194 P1-06/14/15).

Single production seam for ``gate.decided.v1``, ``context.manifested.v1``, and
``brain.think.start`` / ``brain.think.end`` / reasoner spine EPs (via
``publish_ep_bound``). All helpers no-op when no Session is bound (tests / offline).
"""

from __future__ import annotations

import contextlib
from typing import Any

from lca.contracts.harness.memory.events import (
    ContextManifestCommitted,
    GateDecidedCommitted,
)
from lca.contracts.models.cognition.reasoner_turn import ReasonerTurnPlan, ReasonerTurnRender
from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.perceive.perception import ContextItem, ContextManifest
from lca.contracts.models.core.policy.gate_policy import GateDecided
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols import Brain, Reasoner
from lca.contracts.protocols.loop.fact_gateway import AppendReceipt
from lca.loop.fact_gateway import append_catalog_bound, publish_ep_bound


def _gate_decided_committed(event: GateDecided, *, step: int) -> GateDecidedCommitted:
    fact = event.policy_fact
    return GateDecidedCommitted(
        event_id=event.event_id,
        gate=event.gate,
        verdict=event.verdict,
        is_rewritten=event.is_rewritten,
        step=step,
        policy_fact_kind=fact.kind if fact is not None else "",
        policy_fact_message=fact.message if fact is not None else "",
        policy_fact_source=fact.source if fact is not None else "",
        tool_name=event.tool_name,
        rationale=event.rationale,
    )


def _context_item_wire(item: ContextItem) -> dict[str, Any]:
    return {
        "kind": item.kind,
        "payload_repr": repr(item.payload),
        "provenance": item.provenance,
        "extra": dict(item.extra),
    }


def emit_gate_decided(
    session: object,
    event: GateDecidedCommitted,
    *,
    actor: str = "gate",
) -> AppendReceipt | None:
    """Append one ``gate.decided.v1`` fact."""
    return append_catalog_bound(event, session=session, actor=actor)


def emit_gate_decided_from_policy(
    state: AgentState,
    event: GateDecided,
    *,
    session: object | None = None,
    actor: str = "gate",
) -> AppendReceipt | None:
    """Map contracts ``GateDecided`` → session fact; no-op if unbound."""
    return append_catalog_bound(
        _gate_decided_committed(event, step=state.step),
        state=state,
        session=session,
        actor=actor,
    )


def emit_context_manifested(
    session: object,
    manifest: ContextManifest,
    *,
    step: int,
    actor: str = "perceive",
) -> AppendReceipt | None:
    """Append one ``context.manifested.v1`` fact."""
    return append_catalog_bound(
        ContextManifestCommitted(
            step=step,
            digest=manifest.digest,
            items=tuple(_context_item_wire(item) for item in manifest.items),
        ),
        session=session,
        actor=actor,
    )


def emit_context_manifested_for_state(
    state: AgentState,
    manifest: ContextManifest,
    *,
    session: object | None = None,
    actor: str = "perceive",
) -> AppendReceipt | None:
    """Resolve session from run context, then emit manifest fact."""
    return append_catalog_bound(
        ContextManifestCommitted(
            step=state.step,
            digest=manifest.digest,
            items=tuple(_context_item_wire(item) for item in manifest.items),
        ),
        state=state,
        session=session,
        actor=actor,
    )


def emit_brain_think_start_for_state(
    state: AgentState,
    *,
    session: object | None = None,
    actor: str = "brain",
) -> AppendReceipt | None:
    """Append one ``brain.think.start`` spine fact."""
    return publish_ep_bound(
        "brain.think.start",
        {"state_id": state.trace_id},
        state=state,
        session=session,
        actor=actor,
    )


def emit_brain_think_end_for_state(
    state: AgentState,
    *,
    outcome: str = "success",
    session: object | None = None,
    actor: str = "brain",
) -> AppendReceipt | None:
    """Append one ``brain.think.end`` spine fact."""
    return publish_ep_bound(
        "brain.think.end",
        {"state_id": state.trace_id, "outcome": outcome},
        state=state,
        session=session,
        actor=actor,
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
) -> LLMResponse:
    """Run ``Reasoner.generate_thoughts`` with reasoner spine EPs via FactGateway.

    Uses duck-typed ``build_turn_plan`` / ``render_turn`` / ``complete_turn`` when
    present (``PromptReasoner``); otherwise delegates without spine envelope.
    """
    build_turn_plan = getattr(reasoner, "build_turn_plan", None)
    render_turn = getattr(reasoner, "render_turn", None)
    complete_turn = getattr(reasoner, "complete_turn", None)
    if not callable(build_turn_plan) or not callable(render_turn) or not callable(complete_turn):
        return await reasoner.generate_thoughts(state)

    plan: ReasonerTurnPlan = build_turn_plan(state)
    with contextlib.suppress(Exception):
        emit_prompt_assembler_start_for_state(state, plan)
    try:
        render: ReasonerTurnRender = render_turn(state, plan)
    except BaseException:
        with contextlib.suppress(Exception):
            emit_prompt_assembler_end_for_state(
                state,
                plan,
                None,
                outcome="failure",
                section_count=0,
                variant=plan.variant_preview,
            )
        raise
    with contextlib.suppress(Exception):
        emit_prompt_assembler_end_for_state(state, plan, render, outcome="success")
    with contextlib.suppress(Exception):
        _emit_reasoner_meta_from_render(plan, render)
    with contextlib.suppress(Exception):
        emit_reasoner_reason_start_for_state(state, state_id=plan.state_id)
    try:
        response = await complete_turn(state, render)
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
    return response


async def run_brain_think_with_spine_facts(brain: Brain, state: AgentState) -> Decision:
    """Run ``brain.think`` with ``brain.think.start/end`` facts via FactGateway.

    Spine mirror failures must not block cognition (same contract as the former
    ``ModularBrain`` inline envelope).
    """
    with contextlib.suppress(Exception):
        emit_brain_think_start_for_state(state)
    try:
        decision = await brain.think(state)
    except BaseException:
        with contextlib.suppress(Exception):
            emit_brain_think_end_for_state(state, outcome="failure")
        raise
    with contextlib.suppress(Exception):
        emit_brain_think_end_for_state(state, outcome="success")
    return decision


__all__ = [
    "emit_brain_think_end_for_state",
    "emit_brain_think_start_for_state",
    "emit_context_manifested",
    "emit_context_manifested_for_state",
    "emit_critic_eval_end_for_state",
    "emit_critic_eval_start_for_state",
    "emit_gate_decided",
    "emit_gate_decided_from_policy",
    "emit_prompt_assembler_end_for_state",
    "emit_prompt_assembler_start_for_state",
    "emit_reasoner_reason_end_for_state",
    "emit_reasoner_reason_start_for_state",
    "emit_skill_router_route_for_state",
    "emit_synthesizer_merge_for_state",
    "run_brain_think_with_spine_facts",
    "run_reasoner_generate_thoughts_with_spine_facts",
]
