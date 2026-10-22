"""Shared formatting helpers for skill tools."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from lca.contracts.protocols.memory.operational_skills import SkillIndexEntry


def to_market_skill_items(items: tuple[SkillIndexEntry, ...]) -> list[dict[str, Any]]:
    """Project ``SkillIndexEntry`` rows into LobeHub ``SearchSkillState.items`` shape."""
    now = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    out: list[dict[str, Any]] = [
        {
            "identifier": item.skill_id,
            "name": item.name,
            "description": item.summary or "",
            "summary": item.summary or "",
            "installCount": 0,
            "createdAt": now,
            "updatedAt": now,
            **({"version": item.version} if item.version else {}),
            **({"sourceUrl": item.source_url} if item.source_url else {}),
        }
        for item in items
    ]
    return out


def format_skill_index_rows(items: tuple[Any, ...]) -> str:
    if not items:
        return "（无匹配结果）"
    lines: list[str] = [
        f"{idx}. {item.name} ({item.skill_id})\n   {item.summary or '（无摘要）'}"
        for idx, item in enumerate(items, start=1)
    ]
    return "\n".join(lines)
