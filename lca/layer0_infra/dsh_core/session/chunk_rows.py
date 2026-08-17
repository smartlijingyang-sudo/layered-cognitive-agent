"""1:1 port of ``@deepseek-ai/dsh-session/chunk-rows``.

Lossless storage packing for ``assistant/chunk`` delta runs.  Providers stream
token-sized deltas, so a log stores hundreds of near-identical event lines
whose JSON envelopes dwarf their payloads.  This module packs each run of
consecutive same-block delta chunks into ONE storage row.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Union

from lca.layer0_infra.dsh_core.session._llm_types import (
    CallId,
    ReasoningDelta,
    StreamChunk,
    TextDelta,
    ToolCallDelta,
)
from lca.layer0_infra.dsh_core.session.types import SessionEvent

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

_DeltaKind = str  # 'text-delta' | 'reasoning-delta' | 'tool-call-delta'


@dataclass(frozen=True)
class _RunDataBase:
    turn: int
    step: int
    index: int
    dt: list[int]


@dataclass(frozen=True)
class _TextRunData(_RunDataBase):
    texts: list[str]


@dataclass(frozen=True)
class _ToolCallRunData(_RunDataBase):
    id: CallId
    args: list[str]
    name: str | None = None


@dataclass(frozen=True)
class TextChunksRow:
    type: str  # "text-chunks"
    seq0: int
    time0: int
    data: _TextRunData


@dataclass(frozen=True)
class ReasoningChunksRow:
    type: str  # "reasoning-chunks"
    seq0: int
    time0: int
    data: _TextRunData


@dataclass(frozen=True)
class ToolCallChunksRow:
    type: str  # "tool-call-chunks"
    seq0: int
    time0: int
    data: _ToolCallRunData


ChunkRow = Union[TextChunksRow, ReasoningChunksRow, ToolCallChunksRow]
"""A packed run of consecutive delta chunk events, discriminated on ``type``."""

StorageRecord = Union[SessionEvent, ChunkRow]
"""One durable log line's JSON value."""

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MIN_RUN: int = 3

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_record(value: Any) -> bool:
    return isinstance(value, dict)


def _has_exact_keys(value: dict[str, Any], keys: list[str]) -> bool:
    return set(value.keys()) == set(keys)


def _classify(event: SessionEvent) -> str | None:
    """Classify an event for packing."""
    if event.type != "assistant/chunk":
        return None
    # Must have exactly the envelope keys
    event_keys = {"type", "seq", "time", "data"}
    if set(_event_keys(event)) != event_keys:
        return None
    if not _is_safe_int(event.seq) or event.seq < 0 or not _is_safe_int(event.time):
        return None
    data = _event_data(event)
    if not _is_record(data):
        return None
    if set(data.keys()) != {"turn", "step", "chunk"}:
        return None
    if not isinstance(data["turn"], (int, float)) or not isinstance(data["step"], (int, float)):
        return None
    chunk = data["chunk"]
    if not _is_record(chunk):
        return None
    if not isinstance(chunk.get("index"), (int, float)):
        return None
    chunk_type = chunk.get("type")
    if chunk_type in ("text-delta", "reasoning-delta"):
        if _has_exact_keys(chunk, ["type", "index", "text"]) and isinstance(chunk["text"], str):
            return chunk_type
        return None
    if chunk_type == "tool-call-delta":
        shape_ok = (
            _has_exact_keys(chunk, ["type", "index", "id", "argumentsDelta"])
            or (
                _has_exact_keys(chunk, ["type", "index", "id", "name", "argumentsDelta"])
                and isinstance(chunk.get("name"), str)
            )
        )
        if (
            shape_ok
            and isinstance(chunk.get("id"), str)
            and isinstance(chunk.get("argumentsDelta"), str)
        ):
            return chunk_type
        return None
    return None


def _event_keys(event: SessionEvent) -> list[str]:
    """Return the set keys present on an event."""
    keys = ["type", "seq", "time", "data"]
    if event.surfaceOp is not None:
        keys.append("surfaceOp")
    if event.sourceEventSeqs is not None:
        keys.append("sourceEventSeqs")
    if event.ignorable is not None:
        keys.append("ignorable")
    return keys


def _event_data(event: SessionEvent) -> Any:
    return event.data


def _is_safe_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _tool_call_of(event: SessionEvent) -> dict[str, Any]:
    data = event.data
    chunk = data["chunk"] if isinstance(data, dict) else getattr(data, "chunk", None)
    if isinstance(chunk, dict):
        return chunk
    return {"id": getattr(chunk, "id", ""), "name": getattr(chunk, "name", None)}


def _index_of(event: SessionEvent) -> int:
    data = event.data
    chunk = data["chunk"] if isinstance(data, dict) else getattr(data, "chunk", None)
    if isinstance(chunk, dict):
        return chunk["index"]
    return getattr(chunk, "index", 0)


def _continues(prev: SessionEvent, next_: SessionEvent, kind: str) -> bool:
    if next_.seq != prev.seq + 1:
        return False
    if not _is_safe_int(next_.time - prev.time):
        return False
    prev_data = prev.data
    next_data = next_.data
    if isinstance(prev_data, dict):
        pt, ps = prev_data["turn"], prev_data["step"]
    else:
        pt, ps = prev_data.turn, prev_data.step
    if isinstance(next_data, dict):
        nt, ns = next_data["turn"], next_data["step"]
    else:
        nt, ns = next_data.turn, next_data.step
    if nt != pt or ns != ps:
        return False
    if _index_of(next_) != _index_of(prev):
        return False
    if kind != "tool-call-delta":
        return True
    a = _tool_call_of(prev)
    b = _tool_call_of(next_)
    a_name = a.get("name")
    b_name = b.get("name")
    return (
        a["id"] == b["id"]
        and ("name" in a) == ("name" in b)
        and a_name == b_name
    )


def _build_row(kind: str, run: list[SessionEvent]) -> ChunkRow:
    first = run[0]
    first_data = first.data
    if isinstance(first_data, dict):
        turn = first_data["turn"]
        step = first_data["step"]
    else:
        turn = first_data.turn
        step = first_data.step
    idx = _index_of(first)
    dt: list[int] = []
    for i in range(1, len(run)):
        dt.append(run[i].time - run[i - 1].time)

    if kind == "tool-call-delta":
        call = _tool_call_of(first)
        call_id = CallId(call["id"])
        name = call.get("name")
        args = []
        for ev in run:
            chunk = ev.data["chunk"] if isinstance(ev.data, dict) else getattr(ev.data, "chunk", None)
            if isinstance(chunk, dict):
                args.append(chunk["argumentsDelta"])
            else:
                args.append(getattr(chunk, "argumentsDelta", ""))
        data = _ToolCallRunData(
            turn=turn, step=step, index=idx, dt=dt,
            id=call_id, args=args, name=name,
        )
        return ToolCallChunksRow(type="tool-call-chunks", seq0=first.seq, time0=first.time, data=data)

    texts = []
    for ev in run:
        chunk = ev.data["chunk"] if isinstance(ev.data, dict) else getattr(ev.data, "chunk", None)
        if isinstance(chunk, dict):
            texts.append(chunk["text"])
        else:
            texts.append(getattr(chunk, "text", ""))
    text_data = _TextRunData(turn=turn, step=step, index=idx, dt=dt, texts=texts)
    if kind == "text-delta":
        return TextChunksRow(type="text-chunks", seq0=first.seq, time0=first.time, data=text_data)
    return ReasoningChunksRow(type="reasoning-chunks", seq0=first.seq, time0=first.time, data=text_data)


# ---------------------------------------------------------------------------
# pack_chunk_runs
# ---------------------------------------------------------------------------


def pack_chunk_runs(events: list[SessionEvent]) -> list[StorageRecord]:
    """Pack an event batch for storage."""
    out: list[StorageRecord] = []
    kind: str | None = None
    run: list[SessionEvent] = []

    def flush() -> None:
        nonlocal kind, run
        if kind is not None and len(run) >= _MIN_RUN:
            out.append(_build_row(kind, run))
        else:
            out.extend(run)
        kind = None
        run = []

    for event in events:
        k = _classify(event)
        if k is None:
            flush()
            out.append(event)
            continue
        if run:
            last = run[-1]
            if k == kind and _continues(last, event, k):
                run.append(event)
                continue
        flush()
        kind = k
        run = [event]
    flush()
    return out


# ---------------------------------------------------------------------------
# decode_storage_record
# ---------------------------------------------------------------------------


def _malformed(tag: str, why: str) -> None:
    raise ValueError(f"malformed {tag} storage row: {why}")


def _validate_run_data(
    tag: str, data: dict[str, Any], payload_key: str
) -> list[str]:
    if (
        not isinstance(data.get("turn"), (int, float))
        or not isinstance(data.get("step"), (int, float))
        or not isinstance(data.get("index"), (int, float))
    ):
        _malformed(tag, "turn/step/index must be numbers")
    payload = data.get(payload_key)
    if (
        not isinstance(payload, list)
        or len(payload) == 0
        or not all(isinstance(e, str) for e in payload)
    ):
        _malformed(tag, f"{payload_key} must be a non-empty string array")
    dt = data.get("dt")
    if not isinstance(dt, list) or not all(_is_safe_int(g) for g in dt):
        _malformed(tag, "dt must be an array of safe integers")
    if len(dt) != len(payload) - 1:
        _malformed(tag, f"dt length {len(dt)} does not match {len(payload)} members")
    return payload  # type: ignore[return-value]


def _validate_row(value: dict[str, Any], tag: str) -> ChunkRow:
    if set(value.keys()) != {"type", "seq0", "time0", "data"}:
        _malformed(tag, "envelope must be exactly {type, seq0, time0, data}")
    seq0 = value["seq0"]
    if not _is_safe_int(seq0) or seq0 < 0:
        _malformed(tag, "seq0 must be a non-negative safe integer")
    time0 = value["time0"]
    if not _is_safe_int(time0):
        _malformed(tag, "time0 must be a safe integer")
    data = value["data"]
    if not _is_record(data):
        _malformed(tag, "data must be an object")
    payload: list[str]
    if tag == "tool-call-chunks":
        with_name = _has_exact_keys(data, ["turn", "step", "index", "id", "name", "dt", "args"])
        without_name = _has_exact_keys(data, ["turn", "step", "index", "id", "dt", "args"])
        if not with_name and not without_name:
            _malformed(tag, "data must be exactly {turn, step, index, id, name?, dt, args}")
        if not isinstance(data["id"], str):
            _malformed(tag, "id (and name when present) must be strings")
        if with_name and not isinstance(data.get("name"), str):
            _malformed(tag, "id (and name when present) must be strings")
        payload = _validate_run_data(tag, data, "args")
    else:
        if not _has_exact_keys(data, ["turn", "step", "index", "dt", "texts"]):
            _malformed(tag, "data must be exactly {turn, step, index, dt, texts}")
        payload = _validate_run_data(tag, data, "texts")
    # Reconstruction bounds
    if not _is_safe_int(seq0 + len(payload) - 1):
        _malformed(tag, "member seqs must stay safe integers")
    t = time0
    for gap in data["dt"]:
        t += gap
        if not _is_safe_int(t):
            _malformed(tag, "member times must stay safe integers")
    return value  # type: ignore[return-value]


def _expand_row(row: ChunkRow) -> list[SessionEvent]:
    members = row.data.args if isinstance(row, ToolCallChunksRow) else row.data.texts
    events: list[SessionEvent] = []
    time = row.time0
    for k in range(len(members)):
        if k > 0:
            time += row.data.dt[k - 1]
        chunk: StreamChunk
        if isinstance(row, TextChunksRow):
            chunk = TextDelta(type="text-delta", index=row.data.index, text=members[k])
        elif isinstance(row, ReasoningChunksRow):
            chunk = ReasoningDelta(type="reasoning-delta", index=row.data.index, text=members[k])
        else:
            # ToolCallChunksRow
            name = row.data.name
            kw: dict[str, Any] = {}
            if name is not None:
                kw["name"] = name
            chunk = ToolCallDelta(
                type="tool-call-delta",
                index=row.data.index,
                id=row.data.id,
                argumentsDelta=members[k],
                **kw,
            )
        events.append(
            SessionEvent(
                type="assistant/chunk",
                seq=row.seq0 + k,
                time=time,
                data={"turn": row.data.turn, "step": row.data.step, "chunk": chunk},
            )
        )
    return events


def decode_storage_record(value: Any) -> list[SessionEvent]:
    """Decode one parsed JSONL line value into the session event(s) it stores."""
    if not _is_record(value):
        return [value]  # type: ignore[list-item]
    tag = value.get("type")
    if tag not in ("text-chunks", "reasoning-chunks", "tool-call-chunks"):
        return [value]  # type: ignore[list-item]
    return _expand_row(_validate_row(value, tag))
