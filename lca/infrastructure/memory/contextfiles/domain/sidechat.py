"""Side-chat branch memory as one Markdown file per branch.

A side chat owns ``side-chats/<id>/MEMORY.md``. Branch-specific durable
facts live there and never touch the main curated projection. The record
store stays outside this module: the host maps its facts into
``SideChatRecord`` and this module renders or parses the Markdown file.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

_MARKER = re.compile(r"<!-- side-chat: ([A-Za-z0-9_-]+) -->")
_BULLET = re.compile(r"^-\s+(.+)$")


@dataclass(frozen=True, slots=True)
class SideChatRecord:
    """One branch memory sentence with its provenance."""

    record_id: str
    content: str
    source: str = ""
    trigger: str = ""
    recorded_on: str = ""


def chat_slug(chat_id: str) -> str:
    """Validate a side-chat id is a single path segment."""

    value = str(chat_id).strip()
    if not value or value in {".", ".."} or value.startswith("."):
        raise ValueError("chat_id must be a single path segment")
    if any(mark in value for mark in ("/", "\\", "\x00")):
        raise ValueError("chat_id must be a single path segment")
    return value


def render_side_chat_memory(records: Sequence[SideChatRecord]) -> str:
    """Render branch memory records as a Markdown file.

    Each record keeps its id in an HTML comment so retrieval can map a hit
    back to a record even after the file is hand-edited.
    """

    lines = ["# 分支记忆", ""]
    for record in records:
        body = record.content.strip()
        if not body:
            continue
        suffix = f" This came from {record.source.strip() or 'unspecified'} when {record.trigger.strip() or 'unspecified'}"
        if record.recorded_on:
            suffix += f", recorded {record.recorded_on}"
        if body.endswith((".", "。")):
            bullet = f"- {body}{suffix}. <!-- side-chat: {record.record_id} -->"
        else:
            bullet = f"- {body}.{suffix}. <!-- side-chat: {record.record_id} -->"
        lines.append(bullet)
    lines.append("")
    return "\n".join(lines)


def parse_side_chat_memory(text: str) -> tuple[SideChatRecord, ...]:
    """Read branch memory records from a Markdown file.

    Records with the HTML id marker are returned verbatim. Marker-less
    bullets get a stable id derived from their content so hand-written
    branch files still participate in retrieval.
    """

    records: list[SideChatRecord] = []
    for line in text.splitlines():
        stripped = line.strip()
        marker = _MARKER.search(stripped)
        bullet = _BULLET.match(stripped)
        if marker is not None:
            body = _bullet_body(stripped[: marker.start()])
            records.append(
                SideChatRecord(
                    record_id=marker.group(1),
                    content=body,
                    source=_source_of(stripped),
                    trigger=_trigger_of(stripped),
                    recorded_on=_recorded_on(stripped),
                )
            )
            continue
        if bullet is not None:
            content = _strip_suffix(bullet.group(1))
            records.append(
                SideChatRecord(
                    record_id=_content_id(content),
                    content=content,
                    source=_source_of(stripped),
                    trigger=_trigger_of(stripped),
                    recorded_on=_recorded_on(stripped),
                )
            )
    return tuple(records)


def _bullet_body(line: str) -> str:
    """Strip the leading ``- `` marker from a rendered bullet."""

    match = _BULLET.match(line)
    if match is None:
        return _strip_suffix(line)
    return _strip_suffix(match.group(1))


def _strip_suffix(text: str) -> str:
    """Remove the provenance suffix from a rendered bullet."""

    return re.sub(r"\s*This came from .*$", "", text).strip()


def _source_of(line: str) -> str:
    match = re.search(r"This came from ([^ ]+) when ", line)
    return match.group(1) if match else ""


def _trigger_of(line: str) -> str:
    match = re.search(r"when ([^,]+)(?:, recorded [\d-]+)?\.", line)
    return match.group(1).strip() if match else ""


def _recorded_on(line: str) -> str:
    match = re.search(r", recorded (\d{4}-\d{2}-\d{2})\.", line)
    return match.group(1) if match else ""


def _content_id(content: str) -> str:
    import hashlib

    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    return f"sidechat-{digest}"


__all__ = [
    "SideChatRecord",
    "chat_slug",
    "parse_side_chat_memory",
    "render_side_chat_memory",
]
