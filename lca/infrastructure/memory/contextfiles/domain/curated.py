"""Human-readable projection of curated memory claims.

The record store stays outside this module. Callers map their own records
into ``CuratedClaim`` and this module renders ``MEMORY.md``. The projection
is not a second source of truth. The next render replaces the file.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

_SECRET = re.compile(
    r"(?i)(\bsk-[A-Za-z0-9]{8,}\b|\bapi[_-]?key\s*[:=]\s*\S+|\bpassword\s*[:=]\s*\S+)"
)
_CHAR_BUDGET = 12_000

_SECTION_FOR = {
    "fact": "Facts",
    "preference": "Preferences",
}


@dataclass(frozen=True, slots=True)
class CuratedClaim:
    """One active memory sentence, already translated out of the host store.

    ``kind`` is ``fact`` or ``preference`` for rows that appear in the
    projection. Other kinds are ignored. ``recorded_on`` is ``YYYY-MM-DD``
    or empty. The host decides how its clock becomes that date.
    """

    claim_id: str
    kind: str
    body: str
    importance: float = 0.5
    source: str = ""
    trigger: str = ""
    recorded_on: str = ""


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


def render_curated_markdown(
    claims: Sequence[CuratedClaim],
    *,
    char_budget: int = _CHAR_BUDGET,
    source_note: str = "",
) -> str:
    """Render fact and preference claims. Identity stays with the caller.

    ``source_note`` is the host's name for its record store. The domain does
    not know that name.
    """

    chosen = [claim for claim in claims if claim.kind in _SECTION_FOR and claim.body.strip()]
    chosen.sort(key=lambda claim: (-claim.importance, claim.claim_id))
    lead = "这份文件由活跃的结构化记忆记录投影而成。"
    if source_note.strip():
        lead = f"{lead}{source_note.strip()}"
    lines = [
        "# 长期记忆",
        "",
        lead,
        "下次写入会重写本文件。直接改这里不会改记录。",
        "",
    ]
    grouped: dict[str, list[str]] = {"Facts": [], "Preferences": []}
    for claim in chosen:
        section = _SECTION_FOR[claim.kind]
        bullet = _bullet(claim)
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


def _bullet(claim: CuratedClaim) -> str:
    source = claim.source.strip() or "unspecified"
    trigger = claim.trigger.strip() or "unspecified"
    body = claim.body.strip()
    suffix = f" This came from {source} when {trigger}"
    if claim.recorded_on:
        suffix += f", recorded {claim.recorded_on}"
    return f"- {body}.{suffix}." if not body.endswith((".", "。")) else f"- {body}{suffix}."


__all__ = [
    "CuratedClaim",
    "CuratedProjectionReceipt",
    "contains_secret",
    "may_acknowledge_projection",
    "render_curated_markdown",
]
