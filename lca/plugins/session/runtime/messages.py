"""Surface → messages 投影（DSH deriveMessages / deriveEventMessage 对位）。

LCA surface 词表是 spine category(见 ``lca_kernel.events.fold``),不是 dsh
斜杠名;``foldSurface`` + :func:`derive_event_message` 是 deriveMessages 的
纯函数形态,Session 运行时增量缓存见 :meth:`Session.derive_messages`。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from lca.contracts.harness.tasks.session import SessionEvent
from lca_kernel.events.fold import (
    SURFACE_ASSISTANT_TYPE,
    SURFACE_TOOL_RESULT_TYPE,
    SURFACE_USER_TYPE,
    SurfaceFoldResult,
    foldSurface,
)

__all__ = [
    "derive_event_message",
    "derive_messages",
    "export_transcript",
]


def derive_event_message(event: SessionEvent | Mapping[str, Any]) -> dict[str, Any] | None:
    """单事件 → 模型 message dict;非 surface / 空 assistant 返回 None。"""
    if isinstance(event, SessionEvent):
        event_type = event.type
        data = event.data
    else:
        event_type = str(event.get("type") or event.get("category") or "")
        raw = event.get("data") if isinstance(event.get("data"), Mapping) else event.get("payload")
        data = raw if isinstance(raw, Mapping) else {}

    if event_type == SURFACE_USER_TYPE:
        messages = data.get("messages")
        if isinstance(messages, list) and messages:
            last = messages[-1]
            if isinstance(last, Mapping):
                return dict(last)
        content = data.get("content") or data.get("text")
        if isinstance(content, str) and content:
            return {"role": "user", "content": content}
        return None

    if event_type == SURFACE_ASSISTANT_TYPE:
        message = data.get("message")
        if isinstance(message, Mapping):
            content = message.get("content")
            if isinstance(content, list) and len(content) == 0:
                return None
            return dict(message)
        content = data.get("content")
        if isinstance(content, str):
            if not content:
                return None
            return {"role": "assistant", "content": content}
        return None

    if event_type == SURFACE_TOOL_RESULT_TYPE:
        message = data.get("message")
        if isinstance(message, Mapping):
            return dict(message)
        return None

    # LCA session 词表 fallback(无 surfaceOp 的简单路径)
    if event_type == "message.accepted.v1":
        content_ref = data.get("content_ref") or data.get("content")
        if isinstance(content_ref, str) and content_ref:
            return {"role": "user", "content": content_ref}
        return None
    if event_type == "assistant.responded.v1":
        content = data.get("content")
        if isinstance(content, str) and content:
            return {"role": "assistant", "content": content}
        return None

    return None


def derive_messages(events: Iterable[SessionEvent | Mapping[str, Any]]) -> list[dict[str, Any]]:
    """``foldSurface`` + per-node ``derive_event_message`` ≡ DSH ``deriveMessages``。"""
    event_list = tuple(events)
    surface: SurfaceFoldResult = foldSurface(event_list)
    by_seq: dict[int, SessionEvent | Mapping[str, Any]] = {}
    for event in event_list:
        if isinstance(event, SessionEvent):
            by_seq[event.seq] = event
        elif isinstance(event, Mapping):
            seq = event.get("seq")
            if isinstance(seq, int):
                by_seq[seq] = event
    messages: list[dict[str, Any]] = []
    for seq in surface.nodes:
        event = by_seq.get(seq)
        if event is None:
            continue
        msg = derive_event_message(event)
        if msg is not None:
            messages.append(msg)
    return messages


def export_transcript(events: Iterable[SessionEvent | Mapping[str, Any]]) -> list[dict[str, Any]]:
    """仅 surface append-origin 节点的人眼 transcript(DSH transcript 对位)。"""
    from lca_kernel.events.fold import isAppendSurfaceEvent

    event_list = tuple(events)
    surface = foldSurface(event_list)
    by_seq: dict[int, SessionEvent | Mapping[str, Any]] = {}
    for event in event_list:
        if isinstance(event, SessionEvent):
            by_seq[event.seq] = event
        elif isinstance(event, Mapping):
            seq = event.get("seq")
            if isinstance(seq, int):
                by_seq[seq] = event
    transcript: list[dict[str, Any]] = []
    for seq in surface.nodes:
        event = by_seq.get(seq)
        if event is None or not isAppendSurfaceEvent(event):
            continue
        msg = derive_event_message(event)
        if msg is not None:
            transcript.append(msg)
    return transcript
