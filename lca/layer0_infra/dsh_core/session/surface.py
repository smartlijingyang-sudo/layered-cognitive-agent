"""1:1 port of ``@deepseek-ai/dsh-session/surface``.

Surface layer on top of the session event log: an ordered view of events
that produce LLM messages.  The append-only log remains the source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lca.layer0_infra.dsh_core.session._llm_types import Message
from lca.layer0_infra.dsh_core.session.types import (
    ReplaceSurfaceOp,
    SessionEvent,
    SurfaceOp,
)

# ---------------------------------------------------------------------------
# Runtime set of surface-eligible event types
# ---------------------------------------------------------------------------

_SURFACE_EVENT_TYPES: frozenset[str] = frozenset([
    "user/message",
    "assistant/message",
    "tool/result",
])

# ---------------------------------------------------------------------------
# Public predicates
# ---------------------------------------------------------------------------


def is_surface_eligible_type(type_: str) -> bool:
    """Whether an event type can join the model-visible surface."""
    return type_ in _SURFACE_EVENT_TYPES


def is_surface_event(event: SessionEvent) -> bool:
    """Narrow an event to a surface-eligible event carrying its required marker."""
    if event.type not in _SURFACE_EVENT_TYPES:
        return False
    return event.surfaceOp is not None


def is_append_surface_event(event: SessionEvent) -> bool:
    """Narrow to an append-origin surface event."""
    return is_surface_event(event) and event.surfaceOp == "append"


def is_replacement_surface_event(event: SessionEvent) -> bool:
    """Narrow to a surface replacement event."""
    return (
        is_surface_event(event)
        and event.surfaceOp is not None
        and event.surfaceOp != "append"
    )


# ---------------------------------------------------------------------------
# derive_event_message
# ---------------------------------------------------------------------------


def derive_event_message(event: SessionEvent) -> Message | None:
    """Project a single event into the LLM message it derives to.

    Returns ``None`` when the event produces no message — a non-surface event
    (chunk, boundary, log-only record) or an empty-content assistant/message.
    """
    match event.type:
        case "user/message":
            return event.data  # UserMessage
        case "assistant/message":
            msg = event.data.message if hasattr(event.data, "message") else None
            if msg is None:
                return None
            # Skip empty-content assistant/message (hosts only usage).
            if isinstance(msg.content, (list, tuple)) and len(msg.content) == 0:
                return None
            return msg
        case "tool/result":
            msg = event.data.message if hasattr(event.data, "message") else None
            return msg
        case _:
            return None


# ---------------------------------------------------------------------------
# SurfaceFoldResult / SurfaceFoldReplacement / SessionSurface
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SurfaceFoldReplacement:
    """One replacement operation observed while folding a session surface."""

    seq: int
    start: int
    end: int
    shadowedSeqs: list[int]


@dataclass(frozen=True)
class SurfaceFoldResult:
    """Complete result of replaying the surface operations in a session log."""

    nodes: list[int]
    replacements: list[SurfaceFoldReplacement]


class SessionSurface:
    """Readonly live projection of the message-producing session events."""

    @property
    def nodes(self) -> list[int]:
        raise NotImplementedError

    @property
    def replaceGeneration(self) -> int:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Internal fold state
# ---------------------------------------------------------------------------


@dataclass
class _SurfaceFoldState:
    nodes: list[int] = field(default_factory=list)
    replaceGeneration: int = 0


def _create_fold_state() -> _SurfaceFoldState:
    return _SurfaceFoldState()


# ---------------------------------------------------------------------------
# Internal validation helpers
# ---------------------------------------------------------------------------


def _is_event_seq(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_replace_op(value: object) -> bool:
    if not isinstance(value, ReplaceSurfaceOp):
        return False
    return _is_event_seq(value.start) and _is_event_seq(value.end)


def _surface_op_of(event: SessionEvent) -> SurfaceOp | None:
    if not is_surface_eligible_type(event.type):
        if event.surfaceOp is not None:
            raise ValueError(
                f'session event "{event.type}" is not surface-eligible '
                f"and cannot carry surfaceOp"
            )
        if event.sourceEventSeqs is not None:
            raise ValueError(
                f'session event "{event.type}" is not surface-eligible '
                f"and cannot carry sourceEventSeqs"
            )
        return None
    op = event.surfaceOp
    if op is None:
        raise ValueError(
            f'session event "{event.type}" is surface-eligible '
            f"and requires a surfaceOp marker"
        )
    if op == "append":
        return op
    if not isinstance(op, ReplaceSurfaceOp):
        raise ValueError(
            f'session event "{event.type}" carries an invalid surfaceOp'
        )
    if not _is_replace_op(op):
        raise ValueError(
            f'session event "{event.type}" carries an invalid replace surfaceOp'
        )
    return op


def _assert_provenance(
    event: SessionEvent,
    shadowedSeqs: list[int],
) -> None:
    raw = event.sourceEventSeqs
    sources: set[int] = set()
    if raw is not None:
        if not isinstance(raw, list):
            raise ValueError(
                f"sourceEventSeqs on event at seq {event.seq} must be a list when present"
            )
        if len(raw) == 0 and event.type != "assistant/message":
            raise ValueError(
                "sourceEventSeqs must not be empty except on assistant/message"
            )
        non_earlier_source: int | None = None
        for source in raw:
            if not _is_event_seq(source):
                raise ValueError(
                    f'session event "{event.type}" sourceEventSeqs must densely '
                    f"contain non-negative safe integers"
                )
            sources.add(source)
            if non_earlier_source is None and source >= event.seq:
                non_earlier_source = source
        if len(sources) != len(raw):
            raise ValueError("sourceEventSeqs must not contain duplicates")
        if non_earlier_source is not None:
            raise ValueError(
                f"sourceEventSeqs must reference earlier events: "
                f"{non_earlier_source} >= current seq {event.seq}"
            )
    missing = [s for s in shadowedSeqs if s not in sources]
    if missing:
        raise ValueError(
            f"surface replace: sourceEventSeqs must include every shadowed "
            f"surface node; missing {', '.join(str(s) for s in missing)}"
        )


def _replacement_range(
    state: _SurfaceFoldState,
    op: ReplaceSurfaceOp,
) -> tuple[int, int, list[int]]:
    """Return (startIdx, endIdx, shadowedSeqs) without mutating state."""
    try:
        startIdx = state.nodes.index(op.start)
    except ValueError:
        raise ValueError(f"surface replace: start seq {op.start} not found in surface")
    try:
        endIdx = state.nodes.index(op.end)
    except ValueError:
        raise ValueError(f"surface replace: end seq {op.end} not found in surface")
    if startIdx > endIdx:
        raise ValueError(
            f"surface replace: start seq {op.start} (index {startIdx}) is after "
            f"end seq {op.end} (index {endIdx})"
        )
    return startIdx, endIdx, state.nodes[startIdx : endIdx + 1]


def _is_deep_equal_json(a: Any, b: Any) -> bool:
    """Deep structural equality over the JSON value domain."""
    if a is b:
        return True
    if isinstance(a, list) or isinstance(b, list):
        if not isinstance(a, list) or not isinstance(b, list) or len(a) != len(b):
            return False
        return all(_is_deep_equal_json(ai, bi) for ai, bi in zip(a, b, strict=True))
    if not isinstance(a, dict) or not isinstance(b, dict) or a is None or b is None:
        return a == b
    if set(a.keys()) != set(b.keys()):
        return False
    return all(_is_deep_equal_json(a[k], b[k]) for k in a)


def _assert_tool_result_rewrite(
    event: SessionEvent,
    shadowedSeqs: list[int],
    events: list[SessionEvent],
    baseSeq: int,
) -> None:
    if event.type != "tool/result":
        return
    if len(shadowedSeqs) != 1:
        raise ValueError(
            "tool/result surface replacement must rewrite exactly one current node"
        )
    for originalSeq in shadowedSeqs:
        original = events[originalSeq - baseSeq]
        if original is None or original.type != "tool/result":
            raise ValueError(
                "tool/result surface replacement must target a current tool/result"
            )
        # Compare everything except the tool-result content
        original_data = _data_dict(original)
        replacement_data = _data_dict(event)
        original_msg = _msg_dict(original)
        replacement_msg = _msg_dict(event)
        # Null out content for comparison
        original_content = original_msg.get("content", [])
        replacement_content = replacement_msg.get("content", [])
        original_result = original_content[0] if original_content else {}
        replacement_result = replacement_content[0] if replacement_content else {}
        original_rest = dict(original_data)
        replacement_rest = dict(replacement_data)
        original_rest["message"] = {
            **original_msg,
            "content": [{**original_result, "content": None}],
        }
        replacement_rest["message"] = {
            **replacement_msg,
            "content": [{**replacement_result, "content": None}],
        }
        if not _is_deep_equal_json(original_rest, replacement_rest):
            raise ValueError(
                "tool/result surface replacement may change only content"
            )


def _data_dict(event: SessionEvent) -> dict[str, Any]:
    if isinstance(event.data, dict):
        return dict(event.data)
    # dataclass → dict
    if hasattr(event.data, "__dataclass_fields__"):
        from dataclasses import asdict
        return asdict(event.data)
    return {}


def _msg_dict(event: SessionEvent) -> dict[str, Any]:
    data = event.data
    if isinstance(data, dict):
        msg = data.get("message", {})
        if isinstance(msg, dict):
            return dict(msg)
    if hasattr(data, "message"):
        msg = data.message
        if hasattr(msg, "__dataclass_fields__"):
            from dataclasses import asdict
            return asdict(msg)
        if isinstance(msg, dict):
            return dict(msg)
    return {}


# ---------------------------------------------------------------------------
# Plan / apply surface events
# ---------------------------------------------------------------------------


@dataclass
class _ReplacePlan:
    kind: str  # "replace"
    seq: int
    start: int
    end: int
    startIdx: int
    endIdx: int
    shadowedSeqs: list[int]


@dataclass
class _AppendPlan:
    kind: str  # "append"
    seq: int


_SurfacePlan = _AppendPlan | _ReplacePlan


def _plan_surface_event(
    state: _SurfaceFoldState,
    event: SessionEvent,
    expectedSeq: int,
    events: list[SessionEvent],
    baseSeq: int,
) -> _SurfacePlan | None:
    if event.seq != expectedSeq:
        raise ValueError(
            f"session event seq {event.seq} is not contiguous; expected {expectedSeq}"
        )
    surfaceOp = _surface_op_of(event)
    if surfaceOp is None:
        return None
    if surfaceOp == "append":
        _assert_provenance(event, [])
        return _AppendPlan(kind="append", seq=event.seq)
    startIdx, endIdx, shadowedSeqs = _replacement_range(state, surfaceOp)
    _assert_provenance(event, shadowedSeqs)
    _assert_tool_result_rewrite(event, shadowedSeqs, events, baseSeq)
    return _ReplacePlan(
        kind="replace",
        seq=event.seq,
        start=surfaceOp.start,
        end=surfaceOp.end,
        startIdx=startIdx,
        endIdx=endIdx,
        shadowedSeqs=shadowedSeqs,
    )


def _apply_surface_plan(
    state: _SurfaceFoldState,
    plan: _SurfacePlan | None,
) -> SurfaceFoldReplacement | None:
    if plan is None:
        return None
    if plan.kind == "append":
        state.nodes.append(plan.seq)
        return None
    # replace
    state.nodes[plan.startIdx : plan.endIdx + 1] = [plan.seq]
    state.replaceGeneration += 1
    return SurfaceFoldReplacement(
        seq=plan.seq,
        start=plan.start,
        end=plan.end,
        shadowedSeqs=plan.shadowedSeqs,
    )


def _apply_surface_event(
    state: _SurfaceFoldState,
    event: SessionEvent,
    expectedSeq: int,
    events: list[SessionEvent],
    baseSeq: int,
) -> SurfaceFoldReplacement | None:
    plan = _plan_surface_event(state, event, expectedSeq, events, baseSeq)
    return _apply_surface_plan(state, plan)


# ---------------------------------------------------------------------------
# fold_surface
# ---------------------------------------------------------------------------


def fold_surface(events: list[SessionEvent]) -> SurfaceFoldResult:
    """Replay a complete session log through the canonical surface fold."""
    state = _create_fold_state()
    replacements: list[SurfaceFoldReplacement] = []
    for index, event in enumerate(events):
        replacement = _apply_surface_event(state, event, index, events, 0)
        if replacement is not None:
            replacements.append(replacement)
    return SurfaceFoldResult(nodes=list(state.nodes), replacements=replacements)


# ---------------------------------------------------------------------------
# SurfaceManager
# ---------------------------------------------------------------------------


class SurfaceManager(SessionSurface):
    """Incremental ordered surface view and append-boundary validator."""

    def __init__(
        self,
        log: list[SessionEvent],
        baseSeq: int = 0,
    ) -> None:
        self._log = log
        self._baseSeq = baseSeq
        self._state = _create_fold_state()
        self._lastProcessedSeq: int = baseSeq - 1
        self._pendingPlan: tuple[SessionEvent, int, _SurfacePlan | None] | None = None

    def validateNext(self, event: SessionEvent) -> None:
        """Validate the next candidate without mutating the committed surface."""
        if self._lastProcessedSeq < self._baseSeq + len(self._log) - 1:
            self._process_delta()
        expectedSeq = self._baseSeq + len(self._log)
        plan = _plan_surface_event(
            self._state, event, expectedSeq, self._log, self._baseSeq
        )
        self._pendingPlan = (event, expectedSeq, plan)

    @property
    def replaceGeneration(self) -> int:
        if self._lastProcessedSeq < self._baseSeq + len(self._log) - 1:
            self._process_delta()
        return self._state.replaceGeneration

    @property
    def nodes(self) -> list[int]:
        if self._lastProcessedSeq < self._baseSeq + len(self._log) - 1:
            self._process_delta()
        return self._state.nodes

    def _process_delta(self) -> None:
        tailSeq = self._baseSeq + len(self._log) - 1
        seq = self._lastProcessedSeq + 1
        while seq <= tailSeq:
            index = seq - self._baseSeq
            event = self._log[index]
            pending = self._pendingPlan
            if pending is not None and pending[0] is event and pending[1] == seq:
                _apply_surface_plan(self._state, pending[2])
            else:
                _apply_surface_event(self._state, event, seq, self._log, self._baseSeq)
            if pending is not None and pending[1] <= seq:
                self._pendingPlan = None
            self._lastProcessedSeq = seq
            seq += 1
