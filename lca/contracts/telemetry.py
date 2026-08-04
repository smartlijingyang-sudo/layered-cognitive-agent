"""Telemetry vocabulary — closed set of span names and attribute keys.

Application emission uses the ``Telemetry`` protocol
(``lca.contracts.protocols.Telemetry``) and L0 ``bind`` / ``span``.

Example (run edge)::

    from lca.contracts.telemetry import SpanName
    from lca.layer0_infra.observability import bind, span

    with bind(observability):
        with span(SpanName.RUN_TEAM, strategy_key=key):
            ...
"""

from __future__ import annotations

from enum import Enum


class SpanName(str, Enum):
    """Stable span names for full-chain observability."""

    RUN_AGENT = "run.agent"
    RUN_TEAM = "run.team"
    # Emitted at run entry (nested under run.team / run.agent) — scenario card.
    RUN_PLAN = "run.plan"
    LOOP_PHASE_PERCEIVE = "loop.phase.perceive"
    LOOP_PHASE_THINK = "loop.phase.think"
    LOOP_PHASE_ACT = "loop.phase.act"
    LOOP_PHASE_REFLECT = "loop.phase.reflect"
    LLM_CHAT = "llm.chat"
    TOOL_EXECUTE = "tool.execute"
    TRANSPORT_REQUEST = "transport.request"
    TRANSPORT_RESPONSE = "transport.response"
    # Emitted when a repeated delegation is short-circuited by the
    # idempotency ledger  — no transport round-trip happens.
    DELEGATE_CACHE_HIT = "delegate.cache_hit"
    TEAM_STRATEGY = "team.strategy"
    TEAM_MEMBER_INVOKE = "team.member_invoke"
    TEAM_ROUND = "team.round"
    TEAM_SYNTHESIS = "team.synthesis"
    ERROR = "error"


# Attribute keys
ATTR_EVENT = "event"
ATTR_AGENT_ROLE = "agent_role"
ATTR_FROM_ROLE = "from_role"
ATTR_TEAM_ID = "team_id"
ATTR_STRATEGY_KEY = "strategy_key"
ATTR_MANDATE = "mandate"
ATTR_STEP = "step"
ATTR_ACTION_TYPE = "action_type"
ATTR_TOOL_NAME = "tool_name"
ATTR_DELEGATE_TARGET = "delegate_target"
ATTR_DELEGATE_COUNT = "delegate_count"
ATTR_SUBTASK_PREVIEW = "subtask_preview"
ATTR_CALLER_ROLE = "caller_role"
ATTR_CALLEE_ROLE = "callee_role"
ATTR_ROUND = "round"
ATTR_MAX_ROUNDS = "max_rounds"
ATTR_CANDIDATE_COUNT = "candidate_count"
ATTR_SYNTHESIS_METHOD = "synthesis_method"
ATTR_MODEL = "model"
ATTR_OK = "ok"
ATTR_STATUS = "status"
ATTR_PROTOCOL = "protocol"
ATTR_LATENCY_MS = "latency_ms"
ATTR_OBJECTIVE_PREVIEW = "objective_preview"
ATTR_MEMBERS = "members"  # comma-separated roles
ATTR_LEAD_ROLE = "lead_role"
ATTR_PLAN_STEPS = "plan_steps"  # " | "-joined expected steps
# LLM I/O (sanitized previews on llm.chat spans)
ATTR_PROMPT_PREVIEW = "prompt_preview"
ATTR_RESPONSE_PREVIEW = "response_preview"
ATTR_PROMPT_CHARS = "prompt_chars"
ATTR_RESPONSE_CHARS = "response_chars"

# HookEvent → loop phase span (cognitive lifecycle)
HOOK_TO_PHASE_SPAN: dict[str, str] = {
    "pre_perceive": SpanName.LOOP_PHASE_PERCEIVE.value,
    "post_perceive": SpanName.LOOP_PHASE_PERCEIVE.value,
    "pre_think": SpanName.LOOP_PHASE_THINK.value,
    "post_think": SpanName.LOOP_PHASE_THINK.value,
    "pre_act": SpanName.LOOP_PHASE_ACT.value,
    "post_act": SpanName.LOOP_PHASE_ACT.value,
    "pre_reflect": SpanName.LOOP_PHASE_REFLECT.value,
    "post_reflect": SpanName.LOOP_PHASE_REFLECT.value,
}
