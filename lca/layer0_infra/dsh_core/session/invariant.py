"""1:1 port of ``@deepseek-ai/dsh-session/invariant``.

Package-owned relational invariants for the session event log.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lca.layer0_infra.dsh_core.session.repair import TOOL_NOT_STARTED
from lca.layer0_infra.dsh_core.session.types import SessionEvent

PACKAGE_NAME = "@deepseek-ai/dsh-session"

name = "session-invariant"
inject = ["invariants"]

InvariantFailure = Callable[[str], None]
InvariantInstaller = Callable[[Any, InvariantFailure], None]


# ---------------------------------------------------------------------------
# SessionTrace
# ---------------------------------------------------------------------------


class _SessionTrace:
    __slots__ = (
        "lastSeq",
        "nextStep",
        "nextTurn",
        "openStep",
        "openTurn",
        "pendingCalls",
    )

    def __init__(self) -> None:
        self.lastSeq: int = -1
        self.openTurn: int | None = None
        self.openStep: int | None = None
        self.nextTurn: int = 1
        self.nextStep: int = 1
        self.pendingCalls: set[str] = set()


# ---------------------------------------------------------------------------
# Transition types
# ---------------------------------------------------------------------------


class _ScalarsTransition:
    __slots__ = ("lastSeq", "nextStep", "nextTurn", "openStep", "openTurn")

    def __init__(
        self,
        lastSeq: int,
        openTurn: int | None,
        openStep: int | None,
        nextTurn: int,
        nextStep: int,
    ) -> None:
        self.lastSeq = lastSeq
        self.openTurn = openTurn
        self.openStep = openStep
        self.nextTurn = nextTurn
        self.nextStep = nextStep


class _PendingTransition:
    __slots__ = ("callId", "kind")

    def __init__(self, kind: str, callId: str | None = None) -> None:
        self.kind = kind  # "none" | "add" | "delete" | "clear"
        self.callId = callId


class _SessionTraceTransition:
    __slots__ = ("pendingCalls", "scalars")

    def __init__(
        self,
        scalars: _ScalarsTransition,
        pendingCalls: _PendingTransition,
    ) -> None:
        self.scalars = scalars
        self.pendingCalls = pendingCalls


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_open_step(
    trace: _SessionTrace,
    kind: str,
    turn: int,
    step: int,
    fail: InvariantFailure,
) -> None:
    if trace.openTurn != turn or trace.openStep != step:
        fail(
            f"{kind} names turn {turn}/step {step} but open is "
            f"turn {trace.openTurn}/step {trace.openStep}"
        )


def _event_data_attr(event: SessionEvent, attr: str) -> Any:
    data = event.data
    if isinstance(data, dict):
        return data.get(attr)
    return getattr(data, attr, None)


# ---------------------------------------------------------------------------
# validate_event
# ---------------------------------------------------------------------------


def validate_event(
    trace: _SessionTrace,
    event: SessionEvent,
    fail: InvariantFailure,
) -> _SessionTraceTransition:
    if event.seq <= trace.lastSeq:
        fail(f"seq must strictly increase: saw {event.seq} after {trace.lastSeq}")

    open_turn = trace.openTurn
    open_step = trace.openStep
    next_turn = trace.nextTurn
    next_step = trace.nextStep
    pending = _PendingTransition("none")

    match event.type:
        case "turn/start":
            if trace.openTurn is not None:
                fail(
                    f"turn/start {_event_data_attr(event, 'turn')} while turn "
                    f"{trace.openTurn} is still open"
                )
            event_turn = _event_data_attr(event, "turn")
            if event_turn != trace.nextTurn:
                fail(f"turn/start expected turn {trace.nextTurn}, got {event_turn}")
            open_turn = event_turn
            next_step = 1

        case "turn/end":
            event_turn = _event_data_attr(event, "turn")
            if trace.openTurn != event_turn:
                fail(f"turn/end {event_turn} does not match open turn {trace.openTurn}")
            if trace.openStep is not None:
                fail(f"turn/end {event_turn} while step {trace.openStep} is still open")
            open_turn = None
            next_turn += 1

        case "step/start":
            event_turn = _event_data_attr(event, "turn")
            if trace.openTurn != event_turn:
                fail(f"step/start in turn {event_turn} but open turn is {trace.openTurn}")
            if trace.openStep is not None:
                fail(
                    f"step/start {_event_data_attr(event, 'step')} while step "
                    f"{trace.openStep} is still open"
                )
            event_step = _event_data_attr(event, "step")
            if event_step != trace.nextStep:
                fail(
                    f"step/start expected step {trace.nextStep} in turn "
                    f"{event_turn}, got {event_step}"
                )
            open_step = event_step

        case "step/end":
            _require_open_step(
                trace, "step/end",
                _event_data_attr(event, "turn"),
                _event_data_attr(event, "step"),
                fail,
            )
            pending = _PendingTransition("clear")
            open_step = None
            next_step += 1

        case "assistant/chunk":
            _require_open_step(
                trace, "assistant/chunk",
                _event_data_attr(event, "turn"),
                _event_data_attr(event, "step"),
                fail,
            )

        case "assistant/message":
            _require_open_step(
                trace, "assistant/message",
                _event_data_attr(event, "turn"),
                _event_data_attr(event, "step"),
                fail,
            )

        case "tool/call":
            _require_open_step(
                trace, "tool/call",
                _event_data_attr(event, "turn"),
                _event_data_attr(event, "step"),
                fail,
            )
            pending = _PendingTransition("add", _event_data_attr(event, "callId"))

        case "tool/result":
            surface_op = event.surfaceOp
            if surface_op is not None and surface_op != "append":
                if trace.openTurn is None:
                    fail("tool/result surface replacement appended outside any open turn")
                # Early skip: surface replacement already validated, skip rest of case
                pending = _PendingTransition("none")
                # Fall through to scalars assignment below
                scalars = (event.seq, open_turn, open_step, next_turn, next_step)
                return _SessionTraceTransition(scalars=scalars, pending=pending)
            _require_open_step(
                trace, "tool/result",
                _event_data_attr(event, "turn"),
                _event_data_attr(event, "step"),
                fail,
            )
            data = event.data
            if isinstance(data, dict):
                msg = data.get("message", {})
                err = data.get("error")
            else:
                msg = getattr(data, "message", None)
                err = getattr(data, "error", None)
            if isinstance(msg, dict):
                src = msg.get("source", {})
                content = msg.get("content", [])
                call_id = src.get("callId") if isinstance(src, dict) else None
                first_block = content[0] if content else {}
                is_error = first_block.get("isError") if isinstance(first_block, dict) else None
            else:
                src = getattr(msg, "source", {}) if msg else {}
                content = getattr(msg, "content", []) if msg else []
                call_id = getattr(src, "callId", None) if hasattr(src, "callId") else (src.get("callId") if isinstance(src, dict) else None)
                first_block = content[0] if content else {}
                is_error = getattr(first_block, "isError", None) if hasattr(first_block, "isError") else (first_block.get("isError") if isinstance(first_block, dict) else None)
            err_code = err.get("code") if isinstance(err, dict) else getattr(err, "code", None) if err else None
            synthetic_not_started = is_error is True and err_code == TOOL_NOT_STARTED
            if call_id not in trace.pendingCalls and not synthetic_not_started:
                fail(f"tool/result for {call_id} with no prior tool/call in this step")
            pending = _PendingTransition("delete", call_id)

        case "user/message":
            pass

        case "session/end-seed":
            pass

        case "todo/write" | "request/header" | "request/context":
            if trace.openTurn is None:
                fail(
                    f"{event.type} appended outside any open turn "
                    f"(core execution events must be turn-enclosed)"
                )

        case _:
            pass

    return _SessionTraceTransition(
        scalars=_ScalarsTransition(
            lastSeq=event.seq,
            openTurn=open_turn,
            openStep=open_step,
            nextTurn=next_turn,
            nextStep=next_step,
        ),
        pendingCalls=pending,
    )


# ---------------------------------------------------------------------------
# apply_transition
# ---------------------------------------------------------------------------


def apply_transition(
    trace: _SessionTrace,
    transition: _SessionTraceTransition,
) -> None:
    trace.lastSeq = transition.scalars.lastSeq
    trace.openTurn = transition.scalars.openTurn
    trace.openStep = transition.scalars.openStep
    trace.nextTurn = transition.scalars.nextTurn
    trace.nextStep = transition.scalars.nextStep

    match transition.pendingCalls.kind:
        case "none":
            pass
        case "add":
            if transition.pendingCalls.callId is not None:
                trace.pendingCalls.add(transition.pendingCalls.callId)
        case "delete":
            if transition.pendingCalls.callId is not None:
                trace.pendingCalls.discard(transition.pendingCalls.callId)
        case "clear":
            trace.pendingCalls.clear()


# ---------------------------------------------------------------------------
# install / apply
# ---------------------------------------------------------------------------


def install(ctx: Any, fail: InvariantFailure) -> None:
    """Install the session contribution into its child registration fiber."""
    traces: dict[int, _SessionTrace] = {}
    staged: dict[int, tuple[Any, _SessionTrace, _SessionTraceTransition]] = {}

    def fresh_trace() -> _SessionTrace:
        return _SessionTrace()

    def seed_session(session: Any) -> _SessionTrace:
        trace = fresh_trace()
        traces[id(session)] = trace
        for event in session.events:
            apply_transition(trace, validate_event(trace, event, fail))
        return trace

    def trace_for(session: Any) -> _SessionTrace:
        t = traces.get(id(session))
        if t is not None:
            return t
        return seed_session(session)

    # Seed existing sessions
    if hasattr(ctx, "sessions"):
        for session in ctx.sessions.list():
            seed_session(session)

        ctx.on("session/created", lambda session: seed_session(session), global_=True)

        def on_session_event(session: Any, event: SessionEvent) -> None:
            key = id(event)
            entry = staged.get(key)
            if entry is None or entry[0] is not session:
                fail("session/event reached publication without matching pre-commit validation")
                return
            del staged[key]
            apply_transition(entry[1], entry[2])

        ctx.on("session/event", on_session_event, global_=True)

        def on_dispatch(_mode: str, event_name: str, args: tuple[Any, ...]) -> None:
            if event_name != "session/event":
                return
            session = args[0]
            event = args[1]
            trace = trace_for(session)
            transition = validate_event(trace, event, fail)
            staged[id(event)] = (session, trace, transition)

        ctx.on("internal/dispatch", on_dispatch, global_=True)


def apply_(ctx: Any) -> Callable[[], None]:
    """Register the session invariant companion."""
    ctx.invariants.register(PACKAGE_NAME, install)
    return lambda: None
