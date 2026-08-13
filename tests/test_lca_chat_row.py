"""Assistant row reconcile: memory must survive into LobeHub's store."""

from __future__ import annotations

from pathlib import Path

_ROW = (Path("deploy/lobehub/patches/runtime") / "lcaChatRow.ts").read_text(encoding="utf-8")


def is_placeholder(content: object) -> bool:
    if not isinstance(content, str):
        return True
    text = content.strip()
    return text == "" or text == "..."


def persist_missed(memory: dict[str, object], stored: dict[str, object] | None) -> bool:
    if not memory.get("assistantId"):
        return False
    if stored is None:
        content = memory.get("content", "")
        return (not is_placeholder(content)) or int(memory.get("toolCount") or 0) > 0
    if not is_placeholder(memory.get("content")) and is_placeholder(stored.get("content")):
        return True
    tools = stored.get("tools")
    tool_len = len(tools) if isinstance(tools, list) else 0
    return int(memory.get("toolCount") or 0) > 0 and tool_len == 0


def test_ts_exports_the_rule() -> None:
    assert "export function isPlaceholderContent" in _ROW
    assert "export function persistMissed" in _ROW


def test_placeholder_is_ellipsis_or_empty() -> None:
    assert is_placeholder("...")
    assert is_placeholder("  ...  ")
    assert is_placeholder("")
    assert is_placeholder(None)
    assert not is_placeholder("今日新闻速览")


def test_missed_when_store_still_has_ellipsis() -> None:
    memory = {"assistantId": "msg_a", "content": "今日新闻速览", "toolCount": 0}
    assert persist_missed(memory, {"content": "...", "tools": []})
    assert not persist_missed(memory, {"content": "今日新闻速览", "tools": []})


def test_missed_when_tools_did_not_land() -> None:
    memory = {"assistantId": "msg_a", "content": "", "toolCount": 1}
    assert persist_missed(memory, {"content": "", "tools": []})
    assert not persist_missed(memory, {"content": "", "tools": [{"id": "t"}]})


def test_empty_memory_is_not_a_miss() -> None:
    memory = {"assistantId": "msg_a", "content": "", "toolCount": 0}
    assert not persist_missed(memory, {"content": "...", "tools": []})
