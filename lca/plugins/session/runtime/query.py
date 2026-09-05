"""Session 事件查询 —— Wave 5 读面（type/turn/step 过滤 + tool 对齐 fold）。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from lca.contracts.harness.tasks.session import SessionEvent
from lca_kernel.events.fold import SURFACE_TOOL_RESULT_TYPE

__all__ = [
    "ToolInvocationView",
    "filter_session_events",
    "fold_tool_invocations",
]

_TURN_START = frozenset({"turn.started.v1", "turn/start"})
_TURN_END = frozenset({"turn.ended.v1", "turn/end"})
_STEP_START = frozenset({"step.started.v1", "step/start"})
_STEP_END = frozenset({"step.ended.v1", "step/end"})
_TOOL_START = frozenset({"body.tool.execute.start", "spine.body.tool.execute.start"})
_TOOL_END = frozenset(
    {
        "body.tool.execute.end",
        "spine.body.tool.execute.end",
        SURFACE_TOOL_RESULT_TYPE,
    }
)


@dataclass(frozen=True, slots=True)
class ToolInvocationView:
    """tool start/end 按 ``invocation_id`` 对齐后的观察面视图。"""

    invocation_id: str
    tool_name: str | None
    turn: int | None
    step: int | None
    started_seq: int | None
    ended_seq: int | None
    outcome: str | None
    ok: bool | None
    duration_ms: int | None


def filter_session_events(
    events: Iterable[SessionEvent | Mapping[str, Any]],
    *,
    event_type: str | None = None,
    turn: int | None = None,
    step: int | None = None,
) -> tuple[SessionEvent, ...]:
    """按 type / turn / step 过滤 session 事件（纯 fold,无 I/O）。"""
    selected: list[SessionEvent] = []
    current_turn: int | None = None
    current_step: int | None = None
    for raw in events:
        event = _coerce_event(raw)
        etype = event.type
        if etype in _TURN_START:
            value = event.data.get("turn")
            current_turn = value if isinstance(value, int) and not isinstance(value, bool) else None
            current_step = None
        elif etype in _TURN_END:
            current_turn = None
            current_step = None
        elif etype in _STEP_START:
            value = event.data.get("step")
            current_step = value if isinstance(value, int) and not isinstance(value, bool) else None
            tval = event.data.get("turn")
            if isinstance(tval, int) and not isinstance(tval, bool):
                current_turn = tval
        elif etype in _STEP_END:
            current_step = None

        if event_type is not None and etype != event_type:
            continue
        if turn is not None and not _matches_turn(event, turn, current_turn):
            continue
        if step is not None and not _matches_step(event, step, current_step):
            continue
        selected.append(event)
    return tuple(selected)


def fold_tool_invocations(
    events: Iterable[SessionEvent | Mapping[str, Any]],
) -> tuple[ToolInvocationView, ...]:
    """``body.tool.execute.*`` start/end 按 ``invocation_id`` 对齐（Session 读面）。"""
    pending: dict[str, dict[str, Any]] = {}
    views: list[ToolInvocationView] = []
    current_turn: int | None = None
    current_step: int | None = None

    for raw in events:
        event = _coerce_event(raw)
        etype = event.type
        if etype in _TURN_START:
            value = event.data.get("turn")
            current_turn = value if isinstance(value, int) and not isinstance(value, bool) else None
            current_step = None
        elif etype in _TURN_END:
            current_turn = None
            current_step = None
        elif etype in _STEP_START:
            value = event.data.get("step")
            current_step = value if isinstance(value, int) and not isinstance(value, bool) else None
            tval = event.data.get("turn")
            if isinstance(tval, int) and not isinstance(tval, bool):
                current_turn = tval
        elif etype in _STEP_END:
            current_step = None

        if etype in _TOOL_START:
            inv_id = event.data.get("invocation_id")
            if not isinstance(inv_id, str) or not inv_id:
                continue
            pending[inv_id] = {
                "tool_name": _tool_name(event.data),
                "turn": _event_turn(event, current_turn),
                "step": _event_step(event, current_step),
                "started_seq": event.seq,
                "start_time": event.time,
            }
            continue

        if etype not in _TOOL_END:
            continue
        inv_id = event.data.get("invocation_id")
        if not isinstance(inv_id, str) or not inv_id:
            continue
        start = pending.pop(inv_id, None)
        outcome = event.data.get("outcome")
        ok = outcome == "success" if isinstance(outcome, str) else None
        duration_ms = None
        if start is not None and isinstance(start.get("start_time"), int):
            duration_ms = max(0, event.time - int(start["start_time"]))
        views.append(
            ToolInvocationView(
                invocation_id=inv_id,
                tool_name=(start or {}).get("tool_name") or _tool_name(event.data),
                turn=(start or {}).get("turn") or _event_turn(event, current_turn),
                step=(start or {}).get("step") or _event_step(event, current_step),
                started_seq=(start or {}).get("started_seq"),
                ended_seq=event.seq,
                outcome=outcome if isinstance(outcome, str) else None,
                ok=ok,
                duration_ms=duration_ms,
            )
        )

    for inv_id, start in pending.items():
        views.append(
            ToolInvocationView(
                invocation_id=inv_id,
                tool_name=start.get("tool_name"),
                turn=start.get("turn"),
                step=start.get("step"),
                started_seq=start.get("started_seq"),
                ended_seq=None,
                outcome=None,
                ok=None,
                duration_ms=None,
            )
        )
    return tuple(views)


def _coerce_event(raw: SessionEvent | Mapping[str, Any]) -> SessionEvent:
    if isinstance(raw, SessionEvent):
        return raw
    event_type = str(raw.get("type") or raw.get("category") or "")
    seq = raw.get("seq", 0)
    time_val = raw.get("time", 0)
    payload = raw.get("data") if isinstance(raw.get("data"), Mapping) else raw.get("payload")
    data = dict(payload) if isinstance(payload, Mapping) else {}
    return SessionEvent(
        type=event_type,
        seq=int(seq) if isinstance(seq, int) and not isinstance(seq, bool) else 0,
        time=int(time_val) if isinstance(time_val, int) and not isinstance(time_val, bool) else 0,
        data=data,
        session_id=str(raw.get("session_id") or raw.get("run_id") or ""),
    )


def _matches_turn(event: SessionEvent, turn: int, current_turn: int | None) -> bool:
    value = event.data.get("turn")
    if isinstance(value, int) and not isinstance(value, bool) and value == turn:
        return True
    return current_turn == turn


def _matches_step(event: SessionEvent, step: int, current_step: int | None) -> bool:
    value = event.data.get("step")
    if isinstance(value, int) and not isinstance(value, bool) and value == step:
        return True
    return current_step == step


def _event_turn(event: SessionEvent, current_turn: int | None) -> int | None:
    value = event.data.get("turn")
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return current_turn


def _event_step(event: SessionEvent, current_step: int | None) -> int | None:
    value = event.data.get("step")
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return current_step


def _tool_name(data: Mapping[str, Any]) -> str | None:
    for key in ("tool_name", "name"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None
