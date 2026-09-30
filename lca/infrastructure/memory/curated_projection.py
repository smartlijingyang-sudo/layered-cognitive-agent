"""Human-readable projection of active semantic ``MemoryRecord`` rows.

``memory/semantic.json`` stays the record store. ``MEMORY.md`` is rewritten
from the active rows so a person can open one file and see the same facts.
The projection is not a second source of truth. The next semantic write
replaces it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from lca.contracts.atoms.enums.enums import MemoryCategory
from lca.contracts.models.core.conversation.memory import MemoryRecord

_SECRET = re.compile(
    r"(?i)(\bsk-[A-Za-z0-9]{8,}\b|\bapi[_-]?key\s*[:=]\s*\S+|\bpassword\s*[:=]\s*\S+)"
)
_CHAR_BUDGET = 12_000

_SECTION_FOR = {
    MemoryCategory.FACT: "Facts",
    MemoryCategory.PREFERENCE: "Preferences",
}


@dataclass(frozen=True, slots=True)
class CuratedProjectionReceipt:
    """Disk evidence for one projection rewrite.

    ``ok`` is true only when the markdown file was replaced. ``record_ids``
    lists the rows committed by the write that triggered the rewrite, not
    every row already on disk. An acknowledgement may follow only when this
    receipt is ok and ``record_ids`` is non-empty.
    """

    ok: bool
    path: str
    byte_count: int
    record_ids: tuple[str, ...] = ()
    error: str = ""


def contains_secret(content: str) -> bool:
    """Return whether ``content`` carries a credential-shaped token."""

    return _SECRET.search(content) is not None


def may_acknowledge_projection(receipt: CuratedProjectionReceipt | None) -> bool:
    """A user-visible "remembered" claim needs a successful committed write."""

    return (
        receipt is not None and receipt.ok and receipt.byte_count > 0 and bool(receipt.record_ids)
    )


def render_curated_markdown(records: list[MemoryRecord], *, char_budget: int = _CHAR_BUDGET) -> str:
    """Render active fact and preference rows. Identity stays in ``USER.md``."""

    chosen = [
        record
        for record in records
        if not record.deleted and record.category in _SECTION_FOR and record.content.strip()
    ]
    chosen.sort(key=lambda record: (-record.importance, record.record_id))
    lines = [
        "# 长期记忆",
        "",
        "这份文件由活跃的结构化记忆记录投影而成。记录在 `memory/semantic.json`。",
        "下次写入会重写本文件。直接改这里不会改记录。",
        "",
    ]
    grouped: dict[str, list[str]] = {"Facts": [], "Preferences": []}
    for record in chosen:
        section = _SECTION_FOR[record.category]
        bullet = _bullet(record)
        projected = "\n".join(lines + _sections(grouped) + [bullet])
        if len(projected) > char_budget:
            break
        grouped[section].append(bullet)
    lines.extend(_sections(grouped))
    text = "\n".join(lines).rstrip() + "\n"
    return text[:char_budget]


def _sections(grouped: dict[str, list[str]]) -> list[str]:
    lines: list[str] = []
    for title in ("Facts", "Preferences"):
        bullets = grouped[title]
        if not bullets:
            continue
        lines.append(f"## {title}")
        lines.append("")
        lines.extend(bullets)
        lines.append("")
    return lines


def _bullet(record: MemoryRecord) -> str:
    source = _meta(record, "source") or "unspecified"
    trigger = _meta(record, "trigger") or record.source_trace_id or "unspecified"
    body = record.content.strip()
    suffix = f" This came from {source} when {trigger}"
    recorded = _recorded_date(record)
    if recorded:
        suffix += f", recorded {recorded}"
    return f"- {body}.{suffix}." if not body.endswith((".", "。")) else f"- {body}{suffix}."


def _meta(record: MemoryRecord, key: str) -> str:
    if not isinstance(record.metadata, dict):
        return ""
    value = record.metadata.get(key)
    return str(value).strip() if value else ""


def _recorded_date(record: MemoryRecord) -> str:
    if record.created_at_ms is None:
        return ""
    moment = datetime.fromtimestamp(record.created_at_ms / 1000, tz=UTC)
    return moment.strftime("%Y-%m-%d")


__all__ = [
    "CuratedProjectionReceipt",
    "contains_secret",
    "may_acknowledge_projection",
    "render_curated_markdown",
]
