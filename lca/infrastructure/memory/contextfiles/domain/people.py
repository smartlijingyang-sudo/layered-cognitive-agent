"""Person pages and the index projected from them.

A person is one Markdown page. The index is a list of those pages, rewritten
whenever a page changes. The host chooses the directory.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NamedPage:
    """One named Markdown page. People and groups share this shape."""

    slug: str
    name: str
    body: str
    intimacy: float = 0.0


PersonPage = NamedPage


def slug_for(name: str) -> str:
    """Turn a display name into a single path segment."""

    slug = "-".join(name.strip().split())
    if not slug or slug in {".", ".."} or slug.startswith("."):
        raise ValueError("name must be a single path segment")
    if any(mark in slug for mark in ("/", "\\", "\x00")):
        raise ValueError("name must be a single path segment")
    return slug


_INTIMACY = re.compile(r"<!-- intimacy: ([0-9.]+) -->")


def render_person_page(page: NamedPage) -> str:
    """Render one named page. Non-zero intimacy is stored as a comment."""

    lines = [f"# {page.name.strip()}", ""]
    if page.intimacy:
        lines.append(f"<!-- intimacy: {page.intimacy:g} -->")
        lines.append("")
    lines.append(page.body.strip())
    lines.append("")
    return "\n".join(lines)


def parse_person_page(slug: str, text: str) -> NamedPage:
    """Read a named page. A missing heading falls back to ``slug``."""

    lines = text.splitlines()
    name = slug
    start = 0
    intimacy = 0.0
    if lines and lines[0].startswith("# "):
        name = lines[0][2:].strip() or slug
        start = 1
        if start < len(lines) and not lines[start].strip():
            start += 1
    if start < len(lines):
        match = _INTIMACY.match(lines[start].strip())
        if match is not None:
            intimacy = float(match.group(1))
            start += 1
            if start < len(lines) and not lines[start].strip():
                start += 1
    body = "\n".join(lines[start:]).strip()
    return NamedPage(slug=slug, name=name, body=body, intimacy=intimacy)


def render_index(pages: Sequence[NamedPage], *, heading: str) -> str:
    """Render the index under ``heading``, higher intimacy first."""

    lines = [f"# {heading}", ""]
    ordered = sorted(pages, key=lambda item: (-item.intimacy, item.name, item.slug))
    for page in ordered:
        lines.append(f"- [{page.name}]({page.slug}.md)")
    lines.append("")
    return "\n".join(lines)


def render_people_index(pages: Sequence[NamedPage]) -> str:
    """Render the people index in name order."""

    return render_index(pages, heading="人物")


__all__ = [
    "NamedPage",
    "PersonPage",
    "parse_person_page",
    "render_index",
    "render_people_index",
    "render_person_page",
    "slug_for",
]
