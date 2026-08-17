"""1:1 port of ``@deepseek-ai/dsh-tools/invariant.ts``.

Package-owned tool-pipeline invariants: pipeline monotonicity, snapshot
immutability, and code-dispatch enclosure checks.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

PACKAGE_NAME = "@deepseek-ai/dsh-tools"

InvariantFailure = Callable[[str], None]

_ToolStage = str  # "pre" | "execute" | "post"


def _validate_result(
    exec_: Any,
    result: Any,
    fail: InvariantFailure,
) -> None:
    """Validate the immutable final execution/result snapshot."""
    # In Python we don't have Object.isFrozen; we trust the contract
    name = getattr(exec_, "name", "")
    call_id = getattr(exec_, "call_id", "") or getattr(exec_, "callId", "")
    if not name or not str(call_id):
        fail("tools/result execution must carry non-empty name and callId")


def install(ctx: Any, fail: InvariantFailure) -> None:
    """Install monotonic pipeline, final-snapshot, and code-dispatch enclosure checks."""
    stages: dict[int, str] = {}
    open_turns: dict[int, int | None] = {}
    dispatch_roots: dict[int, dict[str, str]] = {}

    def validate_dispatch(session: Any, event: Any) -> None:
        event_type = getattr(event, "type", "")
        if event_type not in ("tool/code-dispatch-start", "tool/code-dispatch"):
            return
        data = getattr(event, "data", {})
        root = str(getattr(data, "root_call_id", "") or data.get("rootCallId", ""))
        parent = str(getattr(data, "parent_call_id", "") or data.get("parentCallId", ""))
        child = str(getattr(data, "sub_call_id", "") or data.get("subCallId", ""))
        if not root or not parent or not child:
            fail(
                f"{event_type} must carry non-empty rootCallId, parentCallId, and subCallId"
            )
            return
        sid = id(session)
        roots = dispatch_roots.get(sid)
        if roots is not None:
            known = roots.get(child)
            if known is not None and known != root:
                fail(f"{event_type} changed rootCallId for subCallId {child}")
            if parent != root and roots.get(parent) != root:
                fail(
                    f"{event_type} parentCallId {parent} does not belong "
                    f"to rootCallId {root}"
                )

    def commit_dispatch(session: Any, event: Any) -> None:
        event_type = getattr(event, "type", "")
        if event_type not in ("tool/code-dispatch-start", "tool/code-dispatch"):
            return
        sid = id(session)
        data = getattr(event, "data", {})
        child = str(getattr(data, "sub_call_id", "") or data.get("subCallId", ""))
        root = str(getattr(data, "root_call_id", "") or data.get("rootCallId", ""))
        roots = dispatch_roots.get(sid, {})
        roots[child] = root
        dispatch_roots[sid] = roots

    def seed(session: Any) -> int | None:
        sid = id(session)
        open_turn: int | None = None
        dispatch_roots[sid] = {}
        events = getattr(session, "events", [])
        for event in events:
            validate_dispatch(session, event)
            commit_dispatch(session, event)
            etype = getattr(event, "type", "")
            if etype == "turn/start":
                data = getattr(event, "data", {})
                open_turn = getattr(data, "turn", None) or data.get("turn")
            elif etype == "turn/end":
                open_turn = None
            elif (
                etype in ("tool/code-dispatch-start", "tool/code-dispatch")
                and open_turn is None
            ):
                fail(f"{etype} appended outside any open turn")
        open_turns[sid] = open_turn
        return open_turn

    def open_turn_for(session: Any) -> int | None:
        sid = id(session)
        cached = open_turns.get(sid)
        if cached is not None or sid in open_turns:
            return cached
        return seed(session)

    # Seed existing sessions
    sessions = getattr(getattr(ctx, "sessions", None), "list", lambda: [])()
    for session in sessions:
        seed(session)

    def on_session_created(session: Any) -> None:
        seed(session)

    def on_session_event(session: Any, event: Any) -> None:
        validate_dispatch(session, event)
        commit_dispatch(session, event)
        etype = getattr(event, "type", "")
        sid = id(session)
        if etype == "turn/start":
            data = getattr(event, "data", {})
            open_turns[sid] = getattr(data, "turn", None) or data.get("turn")
        elif etype == "turn/end":
            open_turns[sid] = None

    def on_internal_dispatch(mode: str, event_name: str, args: tuple[Any, ...]) -> None:
        if event_name == "session/event":
            session = args[0]
            event = args[1]
            validate_dispatch(session, event)
            etype = getattr(event, "type", "")
            if (
                etype in ("tool/code-dispatch-start", "tool/code-dispatch")
                and open_turn_for(session) is None
            ):
                fail(f"{etype} appended outside any open turn")
            return

        if event_name == "tools/pre-execute":
            exec_obj = args[0]
            eid = id(exec_obj)
            if eid in stages:
                fail("tools/pre-execute repeated for one execution")
            stages[eid] = "pre"
            return

        if event_name == "tools/execute":
            exec_obj = args[0]
            eid = id(exec_obj)
            if stages.get(eid) != "pre":
                fail("tools/execute must follow tools/pre-execute")
            stages[eid] = "execute"
            return

        if event_name == "tools/post-execute":
            exec_obj = args[0]
            eid = id(exec_obj)
            previous = stages.get(eid)
            if previous not in ("pre", "execute"):
                fail(
                    "tools/post-execute must follow tools/pre-execute or tools/execute"
                )
            stages[eid] = "post"
            return

        if event_name != "tools/result":
            return
        exec_obj = args[0]
        result = args[1]
        _validate_result(exec_obj, result, fail)
        eid = id(exec_obj)
        stages.pop(eid, None)

    ctx.on("session/created", on_session_created, global_=True)
    ctx.on("session/event", on_session_event, global_=True)
    ctx.on("internal/dispatch", on_internal_dispatch, global_=True)


def apply(ctx: Any) -> Callable[[], None]:
    """Register the tools invariant companion.

    Returns the installed registration's disposer.
    """
    ctx.invariants.register(PACKAGE_NAME, install)
    return lambda: None
