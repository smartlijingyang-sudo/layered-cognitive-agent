"""Shared formatting helpers for skill tools."""

from __future__ import annotations

from typing import Any


def format_skill_index_rows(items: tuple[Any, ...]) -> str:
    if not items:
        return "（无匹配结果）"
    lines: list[str] = []
    for idx, item in enumerate(items, start=1):
        lines.append(f"{idx}. {item.name} ({item.skill_id})\n   {item.summary or '（无摘要）'}")
    return "\n".join(lines)
