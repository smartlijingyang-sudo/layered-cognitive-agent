"""Accumulate streamed tool-call arguments into journal-ready snapshots.

LLM 流式输出工具调用参数时,本模块按 ``tool_call_id`` 累积 raw JSON;
executor 在 args 收齐那一刻调 ``mark_slot_done`` / ``pop_completed_slots``,
对每个完成 slot emit 一次 ToolCallResolved(载荷完整 arguments dict)。

事件账本仅存一帧 ToolCallResolved —— 旧"每 delta 一帧 ToolCallStreaming"
是 UI 中间态误入事实流,本批废。前端若需"打字机"体验,前端在收到
ToolCallResolved 后做本地 prefix 截断渲染,或订阅 provider 的 hint 通道。
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
    """Update ``slots``; return a snapshot dict while still streaming.

    Args 完整后,改由 caller 在收到 ``FUNCTION_CALL_ARGUMENTS_DONE`` 或
    ``COMPLETED`` 事件时调用 ``mark_slot_done`` + ``pop_completed_slots``
    一次取出,各自 emit ``ToolCallResolved`` (本批改造)。旧"每 delta
    一次 ToolCallResolved" 已废。
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
    has_emitted = slot.setdefault("emitted", False)
    if has_emitted and raw == slot["emitted_raw"]:
        return None
    slot["emitted"] = True
    slot["emitted_raw"] = raw
    return {
        "tool_name": name,
        "tool_call_id": (tool_call_id or key),
    }


def mark_slot_done(slots: dict[str, dict[str, Any]], tool_call_id: str) -> None:
    """Mark a single slot as 'args 已收齐',等 pop_completed_slots 一次性取出。"""
    key = (tool_call_id or "").strip()
    if not key:
        return
    slot = slots.get(key)
    if slot is None:
        return
    slot["done"] = True


def pop_completed_slots(slots: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """取出所有 done=True 的 slot,从 ``slots`` 里删除,返回按 raw 长度排序的列表。

    排序目的是让"args 短的先 emit",减小并发交错时 UI 出现错位顺序的概率
    (无关事实正确性 —— 事件携带 ``run_seq`` 是真正的因果序)。
    """
    completed: list[dict[str, Any]] = []
    for key in list(slots.keys()):
        slot = slots.get(key)
        if slot is None or not slot.get("done"):
            continue
        completed.append(
            {
                "tool_name": str(slot.get("name") or ""),
                "tool_call_id": key,
                "raw": str(slot.get("raw") or ""),
            }
        )
        slots.pop(key, None)
    completed.sort(key=lambda s: len(s["raw"]))
    return completed


def parse_completed_slot_args(raw: str) -> dict[str, Any]:
    """Args 收齐后 parse。优先 strict JSON,失败时回退 partial extractor。

    为什么需要回退:LLM 流式发工具调用参数时,长 string value(尤其
    Python 代码)在 JSON 里需要 escape 引号 —— LLM 不严格转义时 strict
    JSON parse 会失败。回退到 ``parse_partial_tool_args`` 用正则定位
    key 起点逐字符读到下一个未转义 ``"``;对 ``code`` 等 partial-string
    字段,即便 raw 不是合法 JSON 也能拿到 value(可能不完整,作为兜底)。
    """
    stripped = (raw or "").strip()
    if not stripped:
        return {}
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        return parsed
    return parse_partial_tool_args(stripped)


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
