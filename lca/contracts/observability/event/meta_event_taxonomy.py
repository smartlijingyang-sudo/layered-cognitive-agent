"""Meta-event taxonomy — high-dimensional observability SSOT for the full run stack.

Every side-effecting seam that operators debug must register here **before** shipping.
New features pick a domain + plane; do not invent parallel vocabularies.

**Run artifact:** all durable facts land in ``traces/runs/<run_id>/<run_id>.spine.jsonl``
(via ``Session.append``). Use ``./scripts/lca-ops debug-run <run_id>`` for family counts.

Planes (session-event-pipeline-spec §3):
- **Session catalog** (``.v1``): turn/step/model/skill meta audit
- **Spine observability** (``spine.*`` / bare EP): llm/body/phase/cognition instrumentation
- **Journal execution**: ToolStarted/Invoked (join via invocation_id) — no ``tool.*.v1``
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal, get_args

from lca.contracts.observability.cursor.loop_cursor import PhaseName

MetaEventDomain = Literal[
    "session",  # turn/step/model/thinking lifecycle
    "cognition",  # prompt assemble, reasoner, skill_router
    "llm",  # llm.call.*, llm.request.header*, thinking.*
    "tool",  # schema publish + body.tool.* + phase.tool.*
    "sandbox",  # body.sandbox.enter/exit
    "skill",  # skill.*.v1 + skill.package.*
    "assistant",  # assistant.* Home + assistant.run.bound
    "integration",  # composio.*
]

MetaEventPlane = Literal["session_catalog", "spine_observability", "journal_execution"]


@dataclass(frozen=True)
class MetaEventSlot:
    domain: MetaEventDomain
    plane: MetaEventPlane
    event_key: str
    closure_module: str
    producer_seam: str
    required_fields: tuple[str, ...] = ()
    debug_run_family: str = ""


# ── Session / LLM ───────────────────────────────────────────────────────────

SESSION_LIFECYCLE_EVENTS: Final[tuple[str, ...]] = (
    "session.created.v1",
    "turn.started.v1",
    "turn.ended.v1",
    "step.started.v1",
    "step.ended.v1",
    "message.accepted.v1",
    "model.requested.v1",
    "model.completed.v1",
    "model.failed.v1",
    "assistant.responded.v1",
    "thinking.delta.v1",
    "thinking.completed.v1",
    "turn.control.v1",
)

LLM_SPINE_EPS: Final[tuple[str, ...]] = (
    "llm.call.start",
    "llm.call.end",
    "llm.stream.token",
    "llm.stream.stall",
    "llm.request.header",
    "llm.request.header.assistant",
    "brain.think.start",
    "brain.think.end",
    "brain.perceive.start",
    "brain.perceive.end",
    "step.thinking.record",
)

# ADR-0194 §1.3: cursor fold EP 与 PhaseName 六步闭集对齐;不含 gate phase。
PHASE_FOLD_SPINE_EPS: Final[tuple[str, ...]] = tuple(
    f"phase.{phase}.fold" for phase in get_args(PhaseName)
)

COGNITION_SPINE_EPS: Final[tuple[str, ...]] = (
    "prompt_assembler.assemble.start",
    "prompt_assembler.assemble.end",
    "reasoner.reason.start",
    "reasoner.reason.end",
    "skill_router.route",
    # Gate 是 Think 子链观测 span,非 loop-cursor phase(ADR-0194 G3)。
    "think.gate.start",
    "think.gate.end",
)

COGNITION_SESSION_EVENTS: Final[tuple[str, ...]] = (
    "prompt.section.published.v1",
    "context.injected.v1",
    "skill.routed.v1",
    "gate.decided.v1",
    "delivery.evidence.v1",
    "convergence.evaluated.v1",
    "prompt.surface.rendered.v1",
)

# ── Skill / Tool / Sandbox ──────────────────────────────────────────────────

SKILL_SESSION_EVENTS: Final[tuple[str, ...]] = (
    "skill.catalog.published.v1",
    "skill.loaded.v1",
    "skill.activated.v1",
    "skill.user_invoked.v1",
    "skill.routed.v1",
    "skill.searched.v1",
)

SKILL_SPINE_EXECUTION_POINTS: Final[tuple[str, ...]] = (
    "skill.package.installed",
    "skill.package.install.failed",
    "skill.package.activated",
    "skill.package.searched",
)

TOOL_SESSION_EVENTS: Final[tuple[str, ...]] = (
    "tool.schema.published.v1",
)

TOOL_EXECUTION_SPINE_EPS: Final[tuple[str, ...]] = (
    "body.tool.execute.start",
    "body.tool.execute.end",
    "body.tool.retry",
    "phase.tool.call.start",
    "phase.tool.call.end",
    "phase.tool.denied",
    "step.tool_call.record",
    "step.tool_result.record",
)

SANDBOX_SPINE_EPS: Final[tuple[str, ...]] = (
    "body.sandbox.enter",
    "body.sandbox.exit",
)

ASSISTANT_SPINE_EPS: Final[tuple[str, ...]] = (
    "assistant.created",
    "assistant.bootstrap.completed",
    "assistant.profile.revised",
    "assistant.skill.installed",
    "assistant.skill.activated",
    "assistant.retired",
)

ASSISTANT_SESSION_EVENTS: Final[tuple[str, ...]] = (
    "assistant.run.bound.v1",
)

# Families surfaced by debug-run [2/8] meta summary
DEBUG_RUN_META_FAMILIES: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("session", ("turn.", "step.started", "step.ended", "message.accepted", "session.created")),
    ("llm", ("llm.", "model.", "thinking.", "brain.think", "step.thinking")),
    (
        "prompt",
        (
            "prompt_assembler",
            "prompt.section",
            "prompt.surface",
            "reasoner.reason",
            "skill_router",
            "think.gate",
            "gate.decided",
            "convergence.evaluated",
            "delivery.evidence",
        ),
    ),
    ("tool", ("body.tool.", "phase.tool.", "step.tool_", "tool.schema")),
    ("sandbox", ("body.sandbox.",)),
    ("skill", ("skill.", "assistant.skill.", "skill.package")),
    ("assistant", ("assistant.",)),
    ("composio", ("composio.",)),
)

META_EVENT_PRODUCER_SEAMS: Final[tuple[MetaEventSlot, ...]] = (
    MetaEventSlot(
        domain="llm",
        plane="spine_observability",
        event_key="llm.call.start",
        closure_module="lca_kernel.events.payloads.spine",
        producer_seam="lca.infrastructure.observability.adapters.adapters.TelemetryLLMAdapter",
        debug_run_family="llm",
    ),
    MetaEventSlot(
        domain="cognition",
        plane="spine_observability",
        event_key="prompt_assembler.assemble.end",
        closure_module="lca_kernel.events.payloads.spine",
        producer_seam="lca.infrastructure.session.cognitive_emit.run_reasoner_generate_thoughts_with_spine_facts",
        debug_run_family="prompt",
    ),
    MetaEventSlot(
        domain="cognition",
        plane="session_catalog",
        event_key="prompt.section.published.v1",
        closure_module="lca.contracts.harness.memory.events",
        producer_seam="lca.infrastructure.observability.meta_event_emit.emit_prompt_sections",
        debug_run_family="prompt",
    ),
    MetaEventSlot(
        domain="tool",
        plane="spine_observability",
        event_key="phase.tool.call.start",
        closure_module="lca_kernel.events.payloads.spine",
        producer_seam="lca.cognition.body.tool_journal_emit.emit_tool_started",
        debug_run_family="tool",
    ),
    MetaEventSlot(
        domain="sandbox",
        plane="spine_observability",
        event_key="body.sandbox.enter",
        closure_module="lca_kernel.events.payloads.spine",
        producer_seam="lca.cognition.body.safe_executor.SimpleSafeExecutor.execute",
        debug_run_family="sandbox",
    ),
    MetaEventSlot(
        domain="skill",
        plane="session_catalog",
        event_key="skill.loaded.v1",
        closure_module="lca.contracts.harness.memory.events",
        producer_seam="lca.infrastructure.observability.meta_event_emit.emit_skill_loaded",
        debug_run_family="skill",
    ),
    MetaEventSlot(
        domain="assistant",
        plane="session_catalog",
        event_key="assistant.run.bound.v1",
        closure_module="lca.contracts.harness.memory.events",
        producer_seam="lca.infrastructure.observability.meta_event_emit.emit_assistant_run_bound",
        debug_run_family="assistant",
    ),
    MetaEventSlot(
        domain="assistant",
        plane="spine_observability",
        event_key="assistant.created",
        closure_module="lca.contracts.observability.closure.assistant_ep_closure",
        producer_seam="lca.plugins.domain.assistant.catalog.plugin",
        debug_run_family="assistant",
    ),
    MetaEventSlot(
        domain="integration",
        plane="spine_observability",
        event_key="composio.tool.executed",
        closure_module="lca.contracts.observability.closure.composio_ep_closure",
        producer_seam="lca.infrastructure.integrations.composio.service.service",
        debug_run_family="composio",
    ),
)


def all_session_meta_event_types() -> frozenset[str]:
    return frozenset(
        {
            *SESSION_LIFECYCLE_EVENTS,
            *COGNITION_SESSION_EVENTS,
            *SKILL_SESSION_EVENTS,
            *TOOL_SESSION_EVENTS,
            *ASSISTANT_SESSION_EVENTS,
        }
    )


def classify_spine_event_key(raw_key: str) -> str | None:
    """Map one spine row key to a debug-run meta family (or None)."""
    for family, prefixes in DEBUG_RUN_META_FAMILIES:
        if any(raw_key.startswith(p) or p in raw_key for p in prefixes):
            return family
    return None


__all__ = [
    "ASSISTANT_SESSION_EVENTS",
    "ASSISTANT_SPINE_EPS",
    "COGNITION_SESSION_EVENTS",
    "COGNITION_SPINE_EPS",
    "DEBUG_RUN_META_FAMILIES",
    "LLM_SPINE_EPS",
    "META_EVENT_PRODUCER_SEAMS",
    "PHASE_FOLD_SPINE_EPS",
    "SANDBOX_SPINE_EPS",
    "SESSION_LIFECYCLE_EVENTS",
    "SKILL_SESSION_EVENTS",
    "SKILL_SPINE_EXECUTION_POINTS",
    "TOOL_EXECUTION_SPINE_EPS",
    "TOOL_SESSION_EVENTS",
    "MetaEventDomain",
    "MetaEventPlane",
    "MetaEventSlot",
    "all_session_meta_event_types",
    "classify_spine_event_key",
]
