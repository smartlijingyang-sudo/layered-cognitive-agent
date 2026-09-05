"""Session durable log 读路径 —— 撕尾截断 + known-types fail-closed（DSH format 对位）。

LCA durable 真值经 ``Session.observe`` → ``SpineFileSink`` 写 spine.jsonl;
本模块消费 **session 形态** JSONL 行(``type``/``seq``/``data``/``ignorable``…),
供 restore / 离线校验 / 破坏性测试复用。
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

from lca.contracts.harness.tasks.session import SessionEvent
from lca.plugins.session.runtime.event_catalog import (
    UnknownSessionEventTypeError,
    validate_event_type_for_read,
)

__all__ = [
    "SessionLogReadError",
    "iter_session_log_lines",
    "load_session_events",
    "parse_session_event_record",
]


class SessionLogReadError(ValueError):
    """Session log 读路径不可恢复错误。"""


def iter_session_log_lines(path: Path) -> Iterator[str]:
    """逐行读 JSONL;末尾无换行的半行按撕尾忽略(DSH torn-tail 语义)。"""
    raw = path.read_text(encoding="utf-8")
    if not raw:
        return
    if raw.endswith("\n"):
        lines = raw.splitlines()
    else:
        # 最后一行无换行 = 未完成写入,丢弃
        *complete, _torn = raw.splitlines()
        lines = complete
    yield from lines


def parse_session_event_record(
    data: dict[str, Any],
    *,
    session_id: str,
    line_no: int,
) -> SessionEvent | None:
    """解析一行 dict → SessionEvent;ignorable 未知 type 返回 None(跳过)。"""
    event_type = str(data.get("type") or data.get("category") or "")
    if not event_type:
        raise SessionLogReadError(f"line {line_no}: missing event type")
    ignorable = bool(data.get("ignorable", False))
    try:
        validate_event_type_for_read(event_type, ignorable=ignorable)
    except UnknownSessionEventTypeError as exc:
        raise SessionLogReadError(str(exc)) from exc
    seq = data.get("seq")
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0:
        raise SessionLogReadError(f"line {line_no}: invalid seq {seq!r}")
    time_val = data.get("time", 0)
    if not isinstance(time_val, int) or time_val < 0:
        raise SessionLogReadError(f"line {line_no}: invalid time {time_val!r}")
    payload = data.get("data") if isinstance(data.get("data"), dict) else data.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    surface_op = data.get("surfaceOp", data.get("surface_op"))
    raw_sources = data.get("sourceEventSeqs", data.get("source_event_seqs"))
    source_seqs: tuple[int, ...] | None = None
    if isinstance(raw_sources, Sequence) and not isinstance(raw_sources, (str, bytes)):
        source_seqs = tuple(int(x) for x in raw_sources)
    visibility = data.get("visibility", "model")
    if visibility not in ("model", "audit", "internal"):
        visibility = "model"
    return SessionEvent(
        type=event_type,
        seq=seq,
        time=time_val,
        data=dict(payload),
        session_id=session_id,
        actor=data.get("actor") if isinstance(data.get("actor"), str) else None,
        provider=data.get("provider") if isinstance(data.get("provider"), str) else None,
        visibility=visibility,  # type: ignore[arg-type]
        ignorable=ignorable,
        surface_op=surface_op,
        source_event_seqs=source_seqs,
    )


def load_session_events(path: Path, *, session_id: str) -> tuple[SessionEvent, ...]:
    """加载 session JSONL;校验 seq 连续;拒读脏 type / 撕尾半行。"""
    events: list[SessionEvent] = []
    for line_no, line in enumerate(iter_session_log_lines(path), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise SessionLogReadError(f"line {line_no}: invalid JSON") from exc
        if not isinstance(data, dict):
            raise SessionLogReadError(f"line {line_no}: expected JSON object")
        parsed = parse_session_event_record(data, session_id=session_id, line_no=line_no)
        if parsed is None:
            continue
        if parsed.seq != len(events):
            raise SessionLogReadError(
                f"line {line_no}: seq {parsed.seq} not contiguous (expected {len(events)})"
            )
        events.append(parsed)
    return tuple(events)
