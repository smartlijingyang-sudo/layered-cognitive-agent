"""Minimal YAML frontmatter parser for SKILL.md (no PyYAML runtime dep)."""

from __future__ import annotations

import re

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Return (frontmatter dict, body). Empty dict when no frontmatter."""
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return {}, text.strip()
    raw_meta, body = match.group(1), match.group(2)
    meta: dict[str, str] = {}
    for line in raw_meta.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            meta[key] = value
    return meta, body.strip()


def skill_title(meta: dict[str, str], fallback: str) -> str:
    name = meta.get("name", "").strip()
    return name or fallback
