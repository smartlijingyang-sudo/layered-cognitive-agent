"""Daily trail flow parsing (``memory/YYYY-MM-DD.md``).

Trail files are the raw interaction evidence. The dream pipeline reads
them alongside the structured episode buffer. This module only parses
Markdown lines into plain entries; mapping to episode facts happens at the
host edge.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

_BULLET = re.compile(r"^\s*-\s+(.+)$")
_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_TRAIL_FILE = re.compile(r"^memory/\d{4}-\d{2}-\d{2}\.md$")
_PREFERENCE = re.compile(r"偏好|以后|不要|必须|记住|严禁|回复要|请记")


class NarrowGateViolationError(RuntimeError):
    """Raised when something tries to overwrite an append-only trail file."""


@dataclass(frozen=True, slots=True)
class TrailEntry:
    """One line of raw trail evidence."""

    content: str
    source: str
    trigger: str
    observed_at_ms: int


def trail_date(filename: str) -> str:
    """Extract ``YYYY-MM-DD`` from a trail file name, or return empty."""

    match = _DATE.search(filename)
    return match.group(1) if match else ""


def parse_trail(text: str, *, source: str, observed_at_ms: int) -> tuple[TrailEntry, ...]:
    """Parse bullet lines from a trail file into entries.

    Headings, blank lines, and HTML comments are skipped. The trigger is the
    source date so provenance renders as ``when YYYY-MM-DD``.
    """

    entries: list[TrailEntry] = []
    for line in text.splitlines():
        match = _BULLET.match(line)
        if match is None:
            continue
        content = match.group(1).strip()
        if not content or content.startswith("<!--"):
            continue
        entries.append(
            TrailEntry(
                content=content,
                source=source,
                trigger=source,
                observed_at_ms=observed_at_ms,
            )
        )
    return tuple(entries)


def render_trail_day(date: str, entries: Sequence[TrailEntry]) -> str:
    """Render one day of trail evidence as a Markdown file."""

    lines = [f"# {date}", ""]
    for entry in entries:
        lines.append(f"- {entry.content}")
    lines.append("")
    return "\n".join(lines)


def is_preference_statement(content: str) -> bool:
    """Return whether a trail line is an explicit preference or instruction."""

    return _PREFERENCE.search(content) is not None


def is_trail_relative(relative_path: str) -> bool:
    """Return whether ``relative_path`` is a daily trail file under the home."""

    return _TRAIL_FILE.match(relative_path.replace("\\", "/")) is not None


__all__ = [
    "NarrowGateViolationError",
    "TrailEntry",
    "is_preference_statement",
    "is_trail_relative",
    "parse_trail",
    "render_trail_day",
    "trail_date",
]
