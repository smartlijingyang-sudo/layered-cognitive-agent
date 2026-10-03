"""Human-readable projection of curated memory claims.

The record store stays outside this module. Callers map their own records
into ``CuratedClaim`` and this module renders ``MEMORY.md``. The projection
is not a second source of truth. The next render replaces the file.
"""

from __future__ import annotations

import base64
import binascii
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

_SECRET = re.compile(
    r"(?i)(\bsk-(?:[A-Za-z0-9]+-){0,3}[A-Za-z0-9]{8,}\b"
    r"|\bapi[ _-]?key\s*[:=]\s*\S+"
    r"|\bpassword\s*[:=]\s*\S+"
    r"|\btoken\s*[:=]\s*\S+"
    r"|\baws_secret_access_key\s*=\s*\S+"
    r"|-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"
    r"|密码\s*[:=]\s*\S+"
    r"|密码\s*(?:是|就是|为)\s*[A-Za-z0-9][A-Za-z0-9+/=_@#$.-]{3,}"
    r"|卡号\s*[:=]\s*\S+)"
)
_B64_BLOB = re.compile(r"[A-Za-z0-9+/_-]{32,}={0,2}")
_CHAR_BUDGET = 12_000
_MISDIAGNOSIS = "此前误诊"

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
    """Return whether ``content`` carries a credential-shaped token.

    A base64 blob is scanned only after it decodes to UTF-8 text that itself
    matches the credential pattern, so an opaque token cannot smuggle an
    ``sk-`` key past the plaintext check.
    """

    if _SECRET.search(content) is not None:
        return True
    for match in _B64_BLOB.finditer(content):
        decoded = _decode_b64(match.group(0))
        if decoded and _SECRET.search(decoded) is not None:
            return True
    return False


def _decode_b64(token: str) -> str:
    padded = token + ("=" * ((4 - len(token) % 4) % 4))
    raw = b""
    try:
        raw = base64.b64decode(padded, validate=True)
    except (binascii.Error, ValueError):
        try:
            raw = base64.urlsafe_b64decode(padded)
        except (binascii.Error, ValueError):
            return ""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return ""


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

    text, _omitted = plan_curated_projection(
        claims, char_budget=char_budget, source_note=source_note
    )
    return text


def render_curated_memory_markdown(
    records: Sequence[Any],
    *,
    char_budget: int = _CHAR_BUDGET,
    source_note: str = "",
) -> str:
    """Pure functional projection of MemoryRecord sequence into MEMORY.md markdown.

    Filters out deleted records and category=IDENTITY. Renders persistent
    ## Preferences and ## Facts skeleton with embedded <!-- id:mem_xxx --> tags.
    """
    claims: list[CuratedClaim] = []
    for r in records:
        if getattr(r, "deleted", False):
            continue
        cat = getattr(r, "category", None)
        cat_val = cat.value if hasattr(cat, "value") else str(cat or "")
        if cat_val == "identity":
            continue
        if contains_secret(str(getattr(r, "content", ""))):
            continue
        metadata = getattr(r, "metadata", None)
        if not isinstance(metadata, dict):
            metadata = {}
        source = str(metadata.get("source") or getattr(r, "source", "") or "user").strip()
        trigger = str(metadata.get("trigger") or "").strip()
        created_at_ms = getattr(r, "created_at_ms", None)
        recorded_on = ""
        if isinstance(created_at_ms, (int, float)) and created_at_ms > 0:
            import datetime
            dt = datetime.datetime.fromtimestamp(created_at_ms / 1000.0, tz=datetime.UTC)
            recorded_on = dt.strftime("%Y-%m-%d")

        claims.append(
            CuratedClaim(
                claim_id=str(getattr(r, "record_id", "") or ""),
                kind=cat_val,
                body=str(getattr(r, "content", "") or ""),
                importance=float(getattr(r, "importance", 0.5) or 0.5),
                source=source,
                trigger=trigger,
                recorded_on=recorded_on,
            )
        )
    return render_curated_markdown(claims, char_budget=char_budget, source_note=source_note)


def plan_curated_projection(
    claims: Sequence[CuratedClaim],
    *,
    char_budget: int = _CHAR_BUDGET,
    source_note: str = "",
) -> tuple[str, tuple[CuratedClaim, ...]]:
    """Render claims and return the ones omitted to stay within ``char_budget``.

    Claims whose body contains ``此前误诊`` stay in the projection even when
    they push the file over the budget. Other claims fill remaining room by
    importance. The omitted list is the archive input.
    """

    chosen = [claim for claim in claims if claim.kind in _SECTION_FOR and claim.body.strip()]
    chosen.sort(key=lambda claim: (-claim.importance, claim.claim_id))
    exempt = [claim for claim in chosen if _MISDIAGNOSIS in claim.body]
    ordinary = [claim for claim in chosen if _MISDIAGNOSIS not in claim.body]
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
    grouped: dict[str, list[str]] = {"Preferences": [], "Facts": []}
    for claim in exempt:
        grouped[_SECTION_FOR[claim.kind]].append(_bullet(claim))
    omitted: list[CuratedClaim] = []
    for claim in ordinary:
        bullet = _bullet(claim)
        projected = "\n".join(lines + _sections(grouped) + [bullet])
        if len(projected) > char_budget:
            omitted.append(claim)
            continue
        grouped[_SECTION_FOR[claim.kind]].append(bullet)
    text = "\n".join(lines + _sections(grouped)).rstrip() + "\n"
    if not exempt:
        text = text[:char_budget]
    return text, tuple(omitted)


def _sections(grouped: dict[str, list[str]]) -> list[str]:
    lines: list[str] = []
    placeholders = {
        "Preferences": "- _（暂无偏好记录）_",
        "Facts": "- _（暂无事实记录）_",
    }
    for title in ("Preferences", "Facts"):
        bullets = grouped.get(title) or []
        lines.append(f"## {title}")
        lines.append("")
        if bullets:
            lines.extend(bullets)
        else:
            lines.append(placeholders[title])
        lines.append("")
    return lines


def _bullet(claim: CuratedClaim) -> str:
    source = claim.source.strip() or "unspecified"
    trigger = claim.trigger.strip() or "unspecified"
    body = claim.body.strip()
    suffix = f" This came from {source} when {trigger}"
    if claim.recorded_on:
        suffix += f", recorded {claim.recorded_on}"
    rendered = f"- {body}.{suffix}." if not body.endswith((".", "。")) else f"- {body}{suffix}."
    if claim.claim_id:
        rendered = f"{rendered} <!-- id:{claim.claim_id} -->"
    return rendered


__all__ = [
    "CuratedClaim",
    "CuratedProjectionReceipt",
    "contains_secret",
    "may_acknowledge_projection",
    "plan_curated_projection",
    "render_curated_markdown",
    "render_curated_memory_markdown",
]

