"""Decision / Observation / Reflection contracts."""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from lca.contracts.atoms.enums.enums import ContentType, DelegationProtocol, ReflectionVerdict
from lca.contracts.atoms.ids.ids import utc_now
from lca.contracts.models.core.execution.external_content import ContentOrigin
from lca.contracts.models.core.execution.task_progress import TaskProgress
from lca.contracts.models.core.state.lifecycle import AgentCard

if TYPE_CHECKING:
    from lca.contracts.models.core.execution.result import Result

__all__ = [
    "HITL_TOOL_NAMES",
    "AgentCard",
    "ContentOrigin",
    "Decision",
    "DelegationSpec",
    "Observation",
    "Reflection",
    "TaskProgress",
    "ToolCall",
    "decision_scope",
    "get_current_decision",
    "requires_human_input",
    "strip_external_instructions_from_delegation",
]


@dataclass
class ToolCall:
    """Single tool invocation: name + arguments + optional idempotency key.

    ``wire_status`` / ``wire_reason`` / ``wire_raw_preview`` are the
    ADR-0047 classification copied from :class:`NativeToolCall`. Empty
    ``arguments`` is not enough to tell "model omitted args" from
    "stream truncated"; Body and repair read these fields.
    """

    call_id: str
    tool_name: str
    arguments: dict[str, Any]
    idempotency_key: str | None = None
    timeout_s: int | None = None
    wire_status: str = "ok"
    wire_reason: str = ""
    wire_raw_preview: str = ""


@dataclass
class DelegationSpec:
    """Ask a teammate: target role/agent + protocol + optional deadline/timeout.

    资源切片优先级（ADR-0049）：``timeout_s`` > ``deadline`` 剩余 >
    父 RunBudget 剩余与 ``DEFAULT_DELEGATION_TIMEOUT_S`` 的解析结果。
    """

    subtask: str
    target_role: str | None = None
    target_agent_id: str | None = None
    target_agent_card: AgentCard | None = None
    context_refs: list[str] = field(default_factory=list)
    deadline: datetime | None = None
    timeout_s: float | None = None
    protocol: DelegationProtocol = DelegationProtocol.INTERNAL


@dataclass(frozen=True)
class Decision:
    """One step's chosen action: type + rationale + tool calls / delegation.

    ``delegations`` is the sole representation of DELEGATE/HANDOFF targets:
    empty = none, one entry = single target, multiple = fan-out.

    ``degraded_from`` records the original ``action_type`` when the decision
    was rewritten by the anti-corruption layer (see ``DegradationPolicy``);
    ``None`` means the decision is native. Provenance flows Decision →
    Observation so hooks and stop policies can see the degradation.

    ADR-0220 §4.2: this DTO is the cross-graph boundary between
    ``concept.decision.classify`` / ``concept.decision.shortcut_try`` /
    ``concept.decision.enforce`` (concept graphs) and ``agent.reasoning.turn``
    → ``agent.action.turn``. ``frozen=True`` enforces the closed boundary;
    the ``extra`` field is the explicitly-named bag for non-typed metadata
    that crosses this seam (no other unknown kwargs are accepted — dataclass
    constructor rejects them).
    """

    decision_id: str
    action_type: str
    rationale: str
    confidence: float
    tool_calls: list[ToolCall] = field(default_factory=list)
    delegations: list[DelegationSpec] = field(default_factory=list)
    response_text: str | None = None
    degraded_from: str | None = None
    schema_version: str = "1.0"
    created_at: datetime = field(default_factory=utc_now)
    extra: dict[str, Any] = field(default_factory=dict)
    # ADR-0214 §3.2:Decision 必填 task_progress 四元组。默认值是兼容
    # 旧测试的占位;cognition emit 方必须显式构造(由
    # tests/integration/test_decision_emit_consume.py 守卫)。
    task_progress: TaskProgress = field(default_factory=TaskProgress)
    # ADR-0235 / PR-5 (L-2 / G-9): typed ``needs_approval`` flag replaces
    # the previous ``extra["needs_approval"]`` metadata smuggle across
    # the cognition → act subgraph boundary. ``False`` means the decision
    # may dispatch directly; ``True`` means ``act.approve.gate`` routes
    # through the HITL interrupt seam (ADR-0228 §2.6).
    needs_approval: bool = False
    # ADR-0292 C2 (follow-up wiring 1, adjudicated 2026-10-05 section 9):
    # typed instruction-source channel on the Decision. ``act.approve.gate``
    # is a pure transform of typed ports -- it cannot see *why* the model
    # chose this action. Producers that emit a decision driven by external
    # content (tool result / web fetch / file read / subagent report)
    # record it here; the gate then consults the two refusal doors
    # (``refuse_external_authorization_claim`` /
    # ``refuse_external_instruction_override``) on the trigger text, and
    # the standing-write tools read the ambient origin (wiring 3).
    # ``None`` = no recorded external drive (legacy producers); the gates
    # treat it as not-externally-driven until a producer marks explicitly.
    content_origin: ContentOrigin | None = None
    """Where the instruction driving this decision came from (ADR-0292 C2).

    ``ContentOrigin.EXTERNAL`` + ``origin_trigger_text`` arms the
    authorization gates; ``None`` (default) means no external drive was
    recorded and the gates stay inert.
    """
    origin_trigger_text: str | None = None
    """The external text (as received, unfenced) that drove this decision.

    Only meaningful when ``content_origin`` is ``ContentOrigin.EXTERNAL``;
    the refusal gates scan this text, never the decision's own rationale.
    """


# ---------------------------------------------------------------------------
# ADR-0292 section 9 wiring 3: ambient Decision (delegation contextvar idiom).
#
# The standing-write tools take no ``origin`` parameter (section-9
# adjudication: per-tool signature changes are N x M surface waste);
# instead they read the instruction source of the decision currently
# executing. Mirrors ``lca/contracts/models/team/delegation/context.py``
# (``get_current_delegator`` + ``delegator_scope``): ``asyncio.create_task``
# copies the context, so tools invoked downstream of ``decision_scope``
# observe the decision that drove them. One mechanism, two gates: the
# approval gate (wiring 1) reads ``Decision.content_origin`` off the typed
# port, the standing-write tools (wiring 3) read it here.
# ---------------------------------------------------------------------------

_current_decision: ContextVar[Decision | None] = ContextVar("lca_current_decision", default=None)


def get_current_decision() -> Decision | None:
    """Return the Decision currently executing, or ``None`` when unbound.

    ``None`` = no decision scope is active (legacy / offline / unit-test
    paths): authorization gates treat it as "no recorded external drive".
    """
    return _current_decision.get()


@contextmanager
def decision_scope(decision: Decision) -> Iterator[None]:
    """Bind *decision* as the ambient executing decision for the wrapped block.

    The production binder is ``concept.effect.execute`` (ADR-0292 section 9
    wiring 3): it wraps tool dispatch so the standing-write tools observe
    the origin of the decision that invoked them. LIFO reset on exit.
    """
    token = _current_decision.set(decision)
    try:
        yield
    finally:
        _current_decision.reset(token)


#: Tool names that pause the run for human input before execution. When a
#: Decision carries one of these calls, ``act.approve.gate`` routes through
#: ``intervene.interrupt`` (ADR-0228) instead of dispatching to the tool.
HITL_TOOL_NAMES: frozenset[str] = frozenset({"askUserQuestion", "request_box_help"})


def requires_human_input(tool_calls: object) -> bool:
    """True when any call names a HITL tool.

    Single home for the ``Decision.needs_approval`` predicate so every
    Decision producer (``think.decision.parse``,
    ``decision.compose.action``, legacy classifier) classifies identically.
    Takes ``object`` and coerces defensively: producers pass ``list``,
    ``tuple`` or ``None``.
    """
    if not isinstance(tool_calls, (list, tuple)):
        return False
    for call in tool_calls:
        name = getattr(call, "tool_name", None)
        if name in HITL_TOOL_NAMES:
            return True
        if name == "send_message":
            args = getattr(call, "arguments", None)
            if isinstance(args, dict) and args.get("type") in ("widget", "secret_request"):
                return True
    return False


@dataclass
class Observation:
    """Outcome of acting on a Decision (tool / delegate / respond)."""

    observation_id: str
    success: bool
    payload: Any
    content_type: ContentType = ContentType.TEXT
    content_origin: ContentOrigin = ContentOrigin.EXTERNAL
    """ADR-0292 C1: origin mark on the event envelope (source of truth).

    Fail-closed default: tool / delegate / transport outcomes are external
    content and carry no instruction authority. Producers of genuinely
    internal observations must set ``ContentOrigin.INTERNAL`` explicitly.
    """
    tool_call_id: str | None = None
    error: str | None = None
    retries_used: int = 0
    latency_ms: int = 0
    degraded_from: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_result(cls, result: Result) -> Observation:
        """Bridge a Result back into an Observation for channel return path."""
        from lca.contracts.atoms.semantic.keys import (
            COMPLETION_EMPTY,
            COMPLETION_FULL,
            COMPLETION_PARTIAL,
            FAILURE_KIND,
            FAILURE_KIND_TRANSIENT,
            OBS_COMPLETION_QUALITY,
        )
        from lca.contracts.models.core.state.lifecycle import TaskStatus

        success = result.status == TaskStatus.COMPLETED
        payload = result.output
        extra: dict[str, Any] = {
            "source_trace_id": result.trace_id,
            "source_total_steps": result.total_steps,
            "source_status": result.status,
        }
        if success:
            extra[OBS_COMPLETION_QUALITY] = COMPLETION_FULL
        elif payload:
            # CANCELED / FAILED 但有 partial 正文（ADR-0049 harvest）
            extra[OBS_COMPLETION_QUALITY] = COMPLETION_PARTIAL
            extra[FAILURE_KIND] = FAILURE_KIND_TRANSIENT
        elif result.status == TaskStatus.CANCELED:
            extra[OBS_COMPLETION_QUALITY] = COMPLETION_EMPTY
            extra[FAILURE_KIND] = FAILURE_KIND_TRANSIENT
        return cls(
            observation_id=f"obs_{result.trace_id}",
            success=success,
            payload=payload,
            error=result.error,
            extra=extra,
        )


@dataclass(frozen=True)
class Reflection:
    """Critic output: verdict + lesson + optional correction Decision.

    ADR-0220 §4.2: this DTO is the cross-graph boundary between
    ``concept.reflection.critique`` (concept graph) and
    ``agent.reflection.turn`` → ``agent.memory.turn``. ``frozen=True``
    enforces the closed boundary; ``extra`` is the explicitly-named bag.
    """

    reflection_id: str
    verdict: ReflectionVerdict
    lesson: str | None = None
    correction: Decision | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Turn:
    """One cognitive step: decision + act result + optional reflection."""

    decision: Decision
    observation: Observation
    reflection: Reflection | None = None
    extra: dict[str, Any] = field(default_factory=dict)


#: Directive-shaped sentence patterns (ADR-0292 C3). Imperative sentences in
#: member reports / delegation text are instructions from an external channel
#: and must never be re-authorized into the next round.
_DIRECTIVE_SENTENCE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\u4e0b\u4e00\u6b65|\u8bf7\u6267\u884c|\u8bf7\u5220\u9664|\u8bf7\u8fd0\u884c|\u6267\u884c\u4ee5\u4e0b|\u7acb\u5373\u6267\u884c|\u63a5\u4e0b\u6765.{0,4}\u6267\u884c"
    ),
    re.compile(
        r"^\s*(?:next[,:]?\s+)?(?:please\s+)?(?:delete|remove|run|execute|drop|destroy|shutdown)\b",
        re.IGNORECASE,
    ),
)

_SENTENCE_BOUNDARY = re.compile(r"(?<=[\u3002\uff01\uff1f.!?])")


def strip_external_instructions_from_delegation(text: str) -> str:
    """ADR-0292 C3: drop directive sentences from delegation text.

    A delegation envelope (ADR-0257) carries only the user's real
    authorization and its boundaries. Member reports are external content
    (C1: fenced data); any "next, please delete Y" directive inside them is
    never re-authorized into the next round -- this strips directive-shaped
    sentences and returns the remaining informational content. Purely
    directive input returns ``""``.

    Best-effort sanitizer, not a parser: it drops sentences that look
    imperative. Informational sentences pass through verbatim.
    """
    kept = [
        sentence
        for sentence in _SENTENCE_BOUNDARY.split(text)
        if sentence and not any(p.search(sentence) for p in _DIRECTIVE_SENTENCE_PATTERNS)
    ]
    return "".join(kept).strip()
