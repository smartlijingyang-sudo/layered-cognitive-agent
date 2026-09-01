"""Accumulate streamed tool-call arguments into journal-ready snapshots.

LobeHub paints the card while arguments are still incomplete. Journal must
do the same: one ``tool_call_id`` from the first name delta through ToolInvoked.

ADR-0101 PR-3:返回 frame 仅含 ``tool_name`` / ``tool_call_id`` —— ToolCallStreaming
event 不再带 ``arguments_preview`` / ``plugin_state`` 字段;完整参数通过
``arguments_ref`` 走 evidence 平面,渲染面在 LobeHub renderer registry 取得。
"""

from __future__ import annotations

import json
from typing import Any

_EMIT_EVERY_CHARS = 160
_PARTIAL_STRING_KEYS = (
    "code",
    "command",
    "content",
    "description",
    "language",
    "skill_id",
    "path",
    "query",
)


def push_tool_call_stream(
    slots: dict[str, dict[str, Any]],
    *,
    tool_name: str | None,
    tool_call_id: str | None,
    arguments_delta: str,
) -> dict[str, Any] | None:
    """Update ``slots``; return a snapshot dict when the card should refresh.

    ADR-0101 followup (2026-09-01): emit on every chunk that grows ``raw``
    so LobeHub can paint the tool card continuously while arguments are
    still streaming. The legacy 160-char throttle caused small payloads
    (e.g. ``{"code": "print(2)"}``) to never emit a partial preview.
    De-duplicates against the last-emitted raw value to avoid duplicate
    frames when the LLM emits an empty delta after the name event.
    """
    key = (tool_call_id or "").strip() or (tool_name or "").strip() or "_"
    slot = slots.setdefault(key, {"name": "", "raw": "", "emitted_raw": ""})
    if tool_name:
        slot["name"] = tool_name
    if arguments_delta:
        slot["raw"] += arguments_delta
    name = str(slot["name"] or "")
    if not name:
        return None
    raw = str(slot["raw"] or "")
    # First emit (slot has never emitted) always fires so the card appears.
    # Subsequent emits fire only when raw grew.
    has_emitted = slot.setdefault("emitted", False)
    if has_emitted and raw == slot["emitted_raw"]:
        return None
    slot["emitted"] = True
    slot["emitted_raw"] = raw
    return {
        "tool_name": name,
        "tool_call_id": (tool_call_id or key),
    }


def parse_partial_tool_args(raw: str) -> dict[str, Any]:
    stripped = (raw or "").strip()
    if not stripped:
        return {}
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        return parsed
    out: dict[str, Any] = {}
    for key in _PARTIAL_STRING_KEYS:
        value = extract_partial_json_string(raw, key)
        if value is not None:
            out[key] = value
    return out


def extract_partial_json_string(raw: str, key: str) -> str | None:
    marker = f'"{key}"'
    idx = raw.find(marker)
    if idx < 0:
        return None
    colon = raw.find(":", idx + len(marker))
    if colon < 0:
        return None
    rest = raw[colon + 1 :].lstrip()
    if not rest.startswith('"'):
        return None
    return _decode_json_string_prefix(rest, 1)


def _decode_json_string_prefix(source: str, start: int) -> str:
    parts: list[str] = []
    escaped = False
    for ch in source[start:]:
        if escaped:
            if ch == "n":
                parts.append("\n")
            elif ch == "t":
                parts.append("\t")
            elif ch == "r":
                parts.append("\r")
            else:
                parts.append(ch)
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            break
        parts.append(ch)
    return "".join(parts)
